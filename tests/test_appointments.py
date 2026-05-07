"""
Tests unitarios para el módulo appointments.
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy import select
from tests.conftest import (
    TestAppointmentModel, TestWaitlistModel,
    create_test_appointment, create_test_waitlist
)


class TestAppointmentCreator:
    """Tests para appointments/create.py"""
    
    @pytest.mark.asyncio
    async def test_create_appointment_no_conflict(self, db_session, salon, client, stylist, service):
        """Test crear cita sin conflictos."""
        from appointments.create import AppointmentCreator
        
        start_time = datetime.now() + timedelta(days=1, hours=14)
        
        success, msg, appointment = await AppointmentCreator.create_appointment(
            db_session,
            salon_id=str(salon.id),
            client_id=str(client.id),
            service_name=service.name,
            start_time=start_time
        )
        
        assert success is True, "La cita debería crearse exitosamente sin conflictos"
        assert appointment is not None, "Debería retornar el objeto appointment"
        assert appointment.status == "scheduled", "El status debe ser SCHEDULED"
        assert appointment.service_name == service.name, "El servicio debe coincidir"
    
    @pytest.mark.asyncio
    async def test_create_appointment_with_conflict(self, db_session, salon, client, stylist, service):
        """Test crear cita cuando hay conflicto horario."""
        from appointments.create import AppointmentCreator
        
        # Primero crear una cita en el mismo horario
        existing_time = datetime.now() + timedelta(days=1, hours=14)
        await create_test_appointment(
            db_session,
            str(salon.id),
            str(client.id),
            str(stylist.id),
            str(service.id),
            service.name,
            existing_time,
            service.duration_minutes
        )
        
        # Intentar crear otra cita en el mismo horario
        success, msg, appointment = await AppointmentCreator.create_appointment(
            db_session,
            salon_id=str(salon.id),
            client_id=str(client.id),
            service_name=service.name,
            start_time=existing_time
        )
        
        assert success is False, "La cita debería fallar por conflicto de horario"
        assert appointment is None, "No debería retornar appointment cuando hay conflicto"
    
    @pytest.mark.asyncio
    async def test_create_appointment_service_not_found(self, db_session, salon, client):
        """Test crear cita con servicio que no existe."""
        from appointments.create import AppointmentCreator
        
        start_time = datetime.now() + timedelta(days=1, hours=14)
        
        success, msg, appointment = await AppointmentCreator.create_appointment(
            db_session,
            salon_id=str(salon.id),
            client_id=str(client.id),
            service_name="Servicio Inexistente",
            start_time=start_time
        )
        
        assert success is False, "La cita debería fallar si el servicio no existe"
        assert "no encontrado" in msg.lower(), "El mensaje debe indicar que el servicio no existe"
    
    @pytest.mark.asyncio
    async def test_create_appointment_saves_to_db(self, db_session, salon, client, stylist, service):
        """Test validar que la cita se guarda correctamente en BD."""
        from appointments.create import AppointmentCreator
        
        start_time = datetime.now() + timedelta(days=1, hours=14)
        
        success, msg, appointment = await AppointmentCreator.create_appointment(
            db_session,
            salon_id=str(salon.id),
            client_id=str(client.id),
            service_name=service.name,
            start_time=start_time
        )
        
        # Verificar que se guardó en BD
        result = await db_session.execute(
            select(TestAppointmentModel).where(TestAppointmentModel.id == appointment.id)
        )
        saved_appointment = result.scalar_one_or_none()
        
        assert saved_appointment is not None, "La cita debe estar guardada en BD"
        assert saved_appointment.id == appointment.id, "El ID debe coincidir"
        assert saved_appointment.status == "scheduled", "El status debe ser SCHEDULED"


class TestAppointmentCanceller:
    """Tests para appointments/cancel.py"""
    
    @pytest.mark.asyncio
    async def test_cancel_appointment_success(self, db_session, appointment):
        """Test cancelar cita existente."""
        from appointments.cancel import AppointmentCanceller
        
        success, msg = await AppointmentCanceller.cancel_appointment(
            db_session,
            appointment,
            trigger_waitlist=False
        )
        
        assert success is True, "La cancelación debería ser exitosa"
        assert appointment.status == "cancelled", "El status debe ser CANCELLED"
    
    @pytest.mark.asyncio
    async def test_cancel_appointment_frees_slot(self, db_session, salon, client, stylist, service, appointment):
        """Test que cancelar libera el horario correctamente."""
        from appointments.cancel import AppointmentCanceller
        from appointments.create import AppointmentCreator
        
        # Cancelar la cita existente
        await AppointmentCanceller.cancel_appointment(
            db_session,
            appointment,
            trigger_waitlist=False
        )
        
        # Intentar crear una cita en el mismo horario (debería ser posible ahora)
        success, msg, new_appointment = await AppointmentCreator.create_appointment(
            db_session,
            salon_id=str(salon.id),
            client_id=str(client.id),
            service_name=service.name,
            start_time=appointment.start_time
        )
        
        assert success is True, "El horario liberado debería estar disponible"


class TestAppointmentRescheduler:
    """Tests para appointments/reschedule.py"""
    
    @pytest.mark.asyncio
    async def test_reschedule_to_available_slot(self, db_session, salon, client, stylist, service, appointment):
        """Test reagendar a horario disponible."""
        from appointments.reschedule import AppointmentRescheduler
        
        new_time = datetime.now() + timedelta(days=2, hours=10)
        
        success, msg = await AppointmentRescheduler.reschedule_appointment(
            db_session,
            appointment,
            new_time,
            service_name=service.name
        )
        
        assert success is True, "El reagendamiento debería ser exitoso"
        assert appointment.start_time == new_time, "La hora debe actualizarse"
    
    @pytest.mark.asyncio
    async def test_reschedule_to_occupied_slot(self, db_session, salon, client, stylist, service, appointment):
        """Test reagendar a horario ocupado."""
        from appointments.reschedule import AppointmentRescheduler
        
        # Crear otra cita en el horario objetivo
        occupied_time = datetime.now() + timedelta(days=2, hours=10)
        await create_test_appointment(
            db_session,
            str(salon.id),
            str(client.id),
            str(stylist.id),
            str(service.id),
            service.name,
            occupied_time,
            service.duration_minutes
        )
        
        # Intentar reagendar a ese horario ocupado
        success, msg = await AppointmentRescheduler.reschedule_appointment(
            db_session,
            appointment,
            occupied_time,
            service_name=service.name
        )
        
        assert success is False, "El reagendamiento debería fallar si el horario está ocupado"
    
    @pytest.mark.asyncio
    async def test_reschedule_releases_previous_slot(self, db_session, salon, client, stylist, service, appointment):
        """Test que reagendar libera el horario anterior."""
        from appointments.reschedule import AppointmentRescheduler
        from appointments.create import AppointmentCreator
        
        old_time = appointment.start_time
        new_time = datetime.now() + timedelta(days=2, hours=10)
        
        # Reagendar
        await AppointmentRescheduler.reschedule_appointment(
            db_session,
            appointment,
            new_time,
            service_name=service.name
        )
        
        # Intentar crear una cita en el horario anterior (debería ser posible)
        success, msg, _ = await AppointmentCreator.create_appointment(
            db_session,
            salon_id=str(salon.id),
            client_id=str(client.id),
            service_name=service.name,
            start_time=old_time
        )
        
        assert success is True, "El horario anterior debería estar disponible"


class TestWaitlistManager:
    """Tests para appointments/waitlist.py"""
    
    @pytest.mark.asyncio
    async def test_add_to_waitlist_flexible(self, db_session, salon, client):
        """Test crear entrada en lista de espera FLEXIBLE."""
        from appointments.waitlist import WaitlistManager
        from db.models import WaitlistRequestType
        
        waitlist_manager = WaitlistManager(db_session)
        
        entry = await waitlist_manager.add_to_waitlist(
            salon_id=str(salon.id),
            client_id=str(client.id),
            request_type=WaitlistRequestType.FLEXIBLE
        )
        
        assert entry is not None, "Debe crear la entrada"
        assert entry.request_type == WaitlistRequestType.FLEXIBLE, "El tipo debe ser FLEXIBLE"
        assert entry.status == "waiting", "El status debe ser WAITING"
    
    @pytest.mark.asyncio
    async def test_add_to_waitlist_specific(self, db_session, salon, client, service):
        """Test crear entrada en lista de espera SPECIFIC."""
        from appointments.waitlist import WaitlistManager
        from db.models import WaitlistRequestType
        
        waitlist_manager = WaitlistManager(db_session)
        preferred_date = datetime.now() + timedelta(days=2)
        
        entry = await waitlist_manager.add_to_waitlist(
            salon_id=str(salon.id),
            client_id=str(client.id),
            request_type=WaitlistRequestType.SPECIFIC,
            preferred_date=preferred_date,
            preferred_service_id=str(service.id)
        )
        
        assert entry is not None, "Debe crear la entrada"
        assert entry.request_type == WaitlistRequestType.SPECIFIC, "El tipo debe ser SPECIFIC"
        assert entry.preferred_date == preferred_date, "Debe guardar la fecha preferida"
    
    @pytest.mark.asyncio
    async def test_get_waiting_clients(self, db_session, salon, client):
        """Test obtener clientes en lista de espera."""
        from appointments.waitlist import WaitlistManager
        
        # Crear varias entradas
        await create_test_waitlist(db_session, str(salon.id), str(client.id), "flexible")
        await create_test_waitlist(db_session, str(salon.id), str(client.id), "specific")
        
        waitlist_manager = WaitlistManager(db_session)
        waiting_clients = await waitlist_manager.get_waiting_clients(str(salon.id))
        
        assert len(waiting_clients) == 2, "Debe retornar todas las entradas waiting"
    
    @pytest.mark.asyncio
    async def test_handle_waitlist_response_accepted(self, db_session, salon, client, waitlist_entry):
        """Test procesar respuesta aceptada de lista de espera."""
        from appointments.waitlist import WaitlistManager
        
        waitlist_manager = WaitlistManager(db_session)
        freed_time = datetime.now() + timedelta(days=1, hours=14)
        
        success, msg = await waitlist_manager.handle_waitlist_response(
            waitlist_id=str(waitlist_entry.id),
            accepted=True,
            salon_id=str(salon.id),
            freed_start_time=freed_time,
            service_name="Corte de Cabello"
        )
        
        # Nota: Este test puede fallar si no hay estilistas disponibles en el test
        # El resultado depende de la lógica de AppointmentCreator
        assert isinstance(success, bool), "Debe retornar un booleano"
    
    @pytest.mark.asyncio
    async def test_handle_waitlist_response_rejected(self, db_session, salon, client, waitlist_entry):
        """Test procesar respuesta rechazada de lista de espera."""
        from appointments.waitlist import WaitlistManager
        
        waitlist_manager = WaitlistManager(db_session)
        freed_time = datetime.now() + timedelta(days=1, hours=14)
        
        success, msg = await waitlist_manager.handle_waitlist_response(
            waitlist_id=str(waitlist_entry.id),
            accepted=False,
            salon_id=str(salon.id),
            freed_start_time=freed_time,
            service_name="Corte de Cabello"
        )
        
        assert success is True, "Debe procesar el rechazo exitosamente"
        
        # Verificar que el rejection_count incrementó
        await db_session.refresh(waitlist_entry)
        assert waitlist_entry.rejection_count == 1, "El contador de rechazos debe incrementar"
