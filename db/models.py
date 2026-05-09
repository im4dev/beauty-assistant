import uuid
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, Numeric, String, DateTime, ForeignKey, Text, Boolean, Integer, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class AppointmentStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    RESCHEDULED = "RESCHEDULED"

class Salon(Base):
    __tablename__ = "salons"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    # El ID que Meta nos da para identificar por qué número entró el mensaje
    wa_phone_number_id = Column(String(50), unique=True, index=True)
    timezone = Column(String(50), default="UTC")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    stylists = relationship("Stylist", back_populates="salon")
    clients = relationship("Client", back_populates="salon")

class Stylist(Base):
    __tablename__ = "stylists"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    salon_id = Column(UUID(as_uuid=True), ForeignKey("salons.id"), nullable=False)
    name = Column(String(255), nullable=False)
    phone_number = Column(String(50)) # WhatsApp del estilista
    specialty = Column(String(255)) # Ej: "Colorista", "Corte Caballero"
    is_active = Column(Boolean, default=True)

    salon = relationship("Salon", back_populates="stylists")
    appointments = relationship("Appointment", back_populates="stylist")

class Client(Base):
    __tablename__ = "clients"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    salon_id = Column(UUID(as_uuid=True), ForeignKey("salons.id"), nullable=False)
    name = Column(String(255))
    wa_id = Column(String(50), nullable=False) # Número de WhatsApp del cliente (ej: 52155...)
    
    salon = relationship("Salon", back_populates="clients")
    appointments = relationship("Appointment", back_populates="client")

class Appointment(Base):
    __tablename__ = "appointments"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    salon_id = Column(UUID(as_uuid=True), ForeignKey("salons.id"), nullable=False)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    stylist_id = Column(UUID(as_uuid=True), ForeignKey("stylists.id"), nullable=False)
    service_id = Column(UUID(as_uuid=True), ForeignKey("services.id"))
    
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    status = Column(SQLEnum(AppointmentStatus), default=AppointmentStatus.SCHEDULED)
    service_name = Column(String(255)) # Ej: "Corte de cabello"
    
    # Recordatorios
    reminder_24h_sent = Column(Boolean, default=False)
    reminder_1h_sent = Column(Boolean, default=False)
    reminder_stylist_30min_sent = Column(Boolean, default=False)
    
    client = relationship("Client", back_populates="appointments")
    stylist = relationship("Stylist", back_populates="appointments")
    service = relationship("Service")

class WaitlistRequestType(str, Enum):
    FLEXIBLE = "flexible"
    SPECIFIC = "specific"

class WaitlistStatus(str, Enum):
    WAITING = "waiting"
    OFFERED = "offered"
    REJECTED = "rejected"
    NO_RESPONSE = "no_response"

class Waitlist(Base):
    __tablename__ = "waitlist"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    salon_id = Column(UUID(as_uuid=True), ForeignKey("salons.id"), nullable=False)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    
    # Tipo de solicitud
    request_type = Column(SQLEnum(WaitlistRequestType), nullable=False)
    
    # Para FLEXIBLE: sin preferencias específicas
    # Para SPECIFIC: preferencias exactas
    preferred_date = Column(DateTime, nullable=True)
    preferred_time = Column(String(5), nullable=True)  # HH:MM format
    preferred_stylist_id = Column(UUID(as_uuid=True), ForeignKey("stylists.id"), nullable=True)
    preferred_service_id = Column(UUID(as_uuid=True), ForeignKey("services.id"), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Estado
    is_notified = Column(Boolean, default=False)
    rejection_count = Column(Integer, default=0)
    status = Column(SQLEnum(WaitlistStatus), default=WaitlistStatus.WAITING)

class SessionState(Base):
    """Guarda el contexto de la conversación con el LLM"""
    __tablename__ = "session_states"
    
    # wa_id es el ID del usuario en WhatsApp
    wa_id = Column(String(50), primary_key=True)
    salon_id = Column(UUID(as_uuid=True), ForeignKey("salons.id"), nullable=False)
    
    # Aquí guardamos el JSON de la conversación o el estado (ej: 'WAITING_FOR_DATE')
    current_step = Column(String(50)) 
    context_data = Column(Text) # JSON string con datos temporales de la cita
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Service(Base):
    __tablename__ = "services"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    salon_id = Column(UUID(as_uuid=True), ForeignKey("salons.id"))
    name = Column(String, nullable=False)        # Ejemplo: "Corte de Cabello"
    category = Column(String)                   # Ejemplo: "Peluquería"
    price = Column(Numeric(10, 2))              # Ejemplo: 15.00
    duration_minutes = Column(Integer, default=30) # ¡Vital para la disponibilidad!
    is_active = Column(Boolean, default=True)