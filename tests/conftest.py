"""
Fixtures y configuración compartida para todos los tests.
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, String, DateTime, Boolean, Integer, Numeric, ForeignKey, select
import uuid

# Usar SQLite in-memory para tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


class Base(DeclarativeBase):
    pass


# Modelos simplificados para tests (usando String para IDs en SQLite)
# Renombrados para evitar conflicto con clases de test
class TestSalonModel(Base):
    __tablename__ = "salons"
    id = Column(String, primary_key=True)
    name = Column(String)
    timezone = Column(String, default="UTC")
    is_active = Column(Boolean, default=True)


class TestClientModel(Base):
    __tablename__ = "clients"
    id = Column(String, primary_key=True)
    salon_id = Column(String, ForeignKey("salons.id"))
    name = Column(String)
    wa_id = Column(String)


class TestStylistModel(Base):
    __tablename__ = "stylists"
    id = Column(String, primary_key=True)
    salon_id = Column(String, ForeignKey("salons.id"))
    name = Column(String)
    is_active = Column(Boolean, default=True)


class TestServiceModel(Base):
    __tablename__ = "services"
    id = Column(String, primary_key=True)
    salon_id = Column(String, ForeignKey("salons.id"))
    name = Column(String)
    duration_minutes = Column(Integer, default=30)
    price = Column(Numeric)
    is_active = Column(Boolean, default=True)


class TestAppointmentModel(Base):
    __tablename__ = "appointments"
    id = Column(String, primary_key=True)
    salon_id = Column(String, ForeignKey("salons.id"))
    client_id = Column(String, ForeignKey("clients.id"))
    stylist_id = Column(String, ForeignKey("stylists.id"))
    service_id = Column(String, ForeignKey("services.id"))
    service_name = Column(String)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    status = Column(String, default="scheduled")
    reminder_24h_sent = Column(Boolean, default=False)
    reminder_1h_sent = Column(Boolean, default=False)


class TestWaitlistModel(Base):
    __tablename__ = "waitlist"
    id = Column(String, primary_key=True)
    salon_id = Column(String, ForeignKey("salons.id"))
    client_id = Column(String, ForeignKey("clients.id"))
    request_type = Column(String, default="flexible")
    preferred_date = Column(DateTime, nullable=True)
    preferred_time = Column(String, nullable=True)
    preferred_stylist_id = Column(String, nullable=True)
    preferred_service_id = Column(String, nullable=True)
    rejection_count = Column(Integer, default=0)
    status = Column(String, default="waiting")
    is_notified = Column(Boolean, default=False)


# Engine para tests
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="function")
async def db_session():
    """Crea una sesión de BD en memoria para cada test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with TestSessionLocal() as session:
        yield session
    
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def salon_data():
    """Datos de prueba para un salón."""
    return {
        "id": str(uuid.uuid4()),
        "name": "Salón Test",
        "timezone": "America/New_York",
        "is_active": True
    }


@pytest.fixture
async def salon(db_session, salon_data):
    """Crea un salón Modelde prueba."""
    salon = TestSalon(**salon_data)
    db_session.add(salon)
    await db_session.commit()
    await db_session.refresh(salon)
    return salon


@pytest.fixture
def stylist_data(salon):
    """Datos de prueba para un estilista."""
    return {
        "id": str(uuid.uuid4()),
        "salon_id": salon.id,
        "name": "María",
        "is_active": True
    }


@pytest.fixture
async def stylist(db_session, stylist_data):
    """Crea un estilista Modelde prueba."""
    stylist = TestStylist(**stylist_data)
    db_session.add(stylist)
    await db_session.commit()
    await db_session.refresh(stylist)
    return stylist


@pytest.fixture
def client_data(salon):
    """Datos de prueba para un cliente."""
    return {
        "id": str(uuid.uuid4()),
        "salon_id": salon.id,
        "name": "Juan Pérez",
        "wa_id": "5931234567890"
    }


@pytest.fixture
async def client(db_session, client_data):
    """Crea un cliente Modelde prueba."""
    client = TestClient(**client_data)
    db_session.add(client)
    await db_session.commit()
    await db_session.refresh(client)
    return client


@pytest.fixture
def service_data(salon):
    """Datos de prueba para un servicio."""
    return {
        "id": str(uuid.uuid4()),
        "salon_id": salon.id,
        "name": "Corte de Cabello",
        "duration_minutes": 30,
        "price": 15.00,
        "is_active": True
    }


@pytest.fixture
async def service(db_session, service_data):
    """Crea un servicio dModele prueba."""
    service = TestService(**service_data)
    db_session.add(service)
    await db_session.commit()
    await db_session.refresh(service)
    return service


@pytest.fixture
def appointment_data(salon, client, stylist, service):
    """Datos de prueba para una cita."""
    now = datetime.now()
    return {
        "id": str(uuid.uuid4()),
        "salon_id": salon.id,
        "client_id": client.id,
        "stylist_id": stylist.id,
        "service_id": service.id,
        "service_name": service.name,
        "start_time": now + timedelta(days=1, hours=14),
        "end_time": now + timedelta(days=1, hours=14, minutes=30),
        "status": "scheduled"
    }


@pytest.fixture
async def appointment(db_session, appointment_data):
    """Crea una cita de prueba.""Model"
    appointment = TestAppointment(**appointment_data)
    db_session.add(appointment)
    await db_session.commit()
    await db_session.refresh(appointment)
    return appointment


@pytest.fixture
def waitlist_data(salon, client, service):
    """Datos de prueba para lista de espera."""
    return {
        "id": str(uuid.uuid4()),
        "salon_id": salon.id,
        "client_id": client.id,
        "request_type": "flexible",
        "preferred_date": datetime.now() + timedelta(days=2),
        "status": "waiting"
    }


@pytest.fixture
async def waitlist_entry(db_session, waitlist_data):
    """Crea una entrada de Modellista de espera de prueba."""
    waitlist = TestWaitlist(**waitlist_data)
    db_session.add(waitlist)
    await db_session.commit()
    await db_session.refresh(waitlist)
    return waitlist


# Helper functions
async def create_test_appointment(db_session, salon_id, client_id, stylist_id, service_id, 
                                  service_name, start_time, duration_minutes=30):
    """Helper para crear citas de prueba."""
    end_time = start_time + timedModelelta(minutes=duration_minutes)
    appointment = TestAppointment(
        id=str(uuid.uuid4()),
        salon_id=salon_id,
        client_id=client_id,
        stylist_id=stylist_id,
        service_id=service_id,
        service_name=service_name,
        start_time=start_time,
        end_time=end_time,
        status="scheduled"
    )
    db_session.add(appointment)
    await db_session.commit()
    await db_session.refresh(appointment)
    return appointment


async def create_test_waitlist(db_session, salon_id, client_id, request_type="flexible"):
    """Helper para crear enModeltradas de lista de espera."""
    waitlist = TestWaitlist(
        id=str(uuid.uuid4()),
        salon_id=salon_id,
        client_id=client_id,
        request_type=request_type,
        status="waiting"
    )
    db_session.add(waitlist)
    await db_session.commit()
    await db_session.refresh(waitlist)
    return waitlist
