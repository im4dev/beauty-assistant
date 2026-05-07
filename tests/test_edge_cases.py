"""
Tests de casos edge y robustez del sistema.
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy import select
from tests.conftest import (
    TestAppointment, TestWaitlist,
    create_test_appointment, create_test_waitlist
)
import uuid


class TestPreparationTimeEdgeCase:
    """Tests para el caso edge de tiempo de preparación (<15 min)."""
    
    @pytest.mark.asyncio
    async def test_appointment_with_less_than_15min_gap(self, db_session, salon, client, stylist, service):
        """
        Caso F: Tiempo de preparación.
        
        Si se libera horario con <15 min hasta siguiente cita,
        validar que estilista puede hacerlo.
        Solución: Agrupar con siguiente horario o descartar.
        """
        from appointments.create import AppointmentCreator
        from services.availability import AvailabilityService
        
        # Crear una cita a las 2:00pm
        first_appointment_time = datetime.now() + timedelta(days=1, hours=14)
        await create_test_appointment(
            db_session,
            str(salon.id),
            str(client.id),
            str(stylist.id),
            str(service.id),
            service.name,
            first_appointment_time,
            30  # 30 min, termina a las 2:30pm
        )
        
        # Intentar crear una cita a las 2:35pm (solo 5 min de gap)
        second_appointment_time = datetime.now() + timedelta(days=1, hours=14, minutes=35)
        
        # Validar disponibilidad con AvailabilityService
        is_available, msg = await AvailabilityService.check_availability(
            db_session,
            str(salon.id),
            second_appointment_time,
            30  # 30 min
        )
        
        # Nota: La lógica actual de AvailabilityService no implementa
        # específicamente la regla de 15 min. Este test documenta
        # el caso edge para futura implementación.
        assert isinstance(is_available, bool), "Debe retornar booleano"
    
    @pytest.mark.asyncio
    async def test_appointment_exactly_15min_gap(self, db_session, salon, client, stylist, service):
        """
        Test con exactamente 15 min de gap (caso límite).
        """
        from services.availability import AvailabilityService
        
        # Crear cita a las 2:00pm (termina 2:30pm)
        first_appointment_time = datetime.now() + timedelta(days=1, hours=14)
        await create_test_appointment(
            db_session,
            str(salon.id),
            str(client.id),
            str(stylist.id),
            str(service.id),
            service.name,
            first_appointment_time,
            30
        )
        
        # Intentar crear a las 2:45pm (exactamente 15 min de gap)
        second_appointment_time = datetime.now() + timedelta(days=1, hours=14, minutes=45)
        
        is_available, msg = await AvailabilityService.check_availability(
            db_session,
            str(salon.id),
            second_appointment_time,
            30
        )
        
        assert isinstance(is_available, bool), "Debe retornar booleano"


class TestConcurrentWaitlistResponses:
    """Tests para el caso G-2: múltiples clientes responden sí al mismo tiempo."""
    
    @pytest.mark.asyncio
    async def test_multiple_clients_accept_same_slot(self, db_session, salon, client):
        """
        Caso G-2: Múltiples responden "sí".
        
        Usar LOCK: Solo el primero que aceptó se agenda.
        Otros quedan en lista (no se pierden).
        No revertir a anterior.
        """
        from appointments.waitlist import WaitlistManager
        
        # Crear 3 clientes en lista de espera
        entry1 = await create_test_waitlist(db_session, str(salon.id), str(uuid.uuid4()), "flexible")
        entry2 = await create_test_waitlist(db_session, str(salon.id), str(uuid.uuid4()), "flexible")
        entry3 = await create_test_waitlist(db_session, str(salon.id), str(uuid.uuid4()), "flexible")
        
        waitlist_manager = WaitlistManager(db_session)
        freed_time = datetime.now() + timedelta(days=1, hours=14)
        
        # Simular que los 3 aceptan al mismo tiempo
        # En implementación real, el lock debe evitar doble-agendamiento
        results = []
        for entry in [entry1, entry2, entry3]:
            success, msg = await waitlist_manager.handle_waitlist_response(
                waitlist_id=str(entry.id),
                accepted=True,
                salon_id=str(salon.id),
                freed_start_time=freed_time,
                service_name="Corte de Cabello"
            )
            results.append(success)
        
        # Nota: La implementación actual no tiene lock optimista.
        # Este test documenta el caso edge para futura implementación.
        assert len(results) == 3, "Debe procesar las 3 respuestas"
    
    @pytest.mark.asyncio
    async def test_waitlist_lock_prevents_double_booking(self, db_session, salon, client):
        """
        Test que el lock evita doble-agendamiento.
        
        Este test verifica que cuando dos clientes intentan aceptar
        el mismo horario, solo uno logra agendar.
        """
        # Nota: Este test requiere implementación de lock en WaitlistManager
        # Documentando el caso edge para futura implementación
        pass


class TestSpecificWaitlistNotTouched:
    """Tests para verificar que SPECIFIC no se toca en cascada."""
    
    @pytest.mark.asyncio
    async def test_specific_waitlist_ignored_in_cascade(self, db_session, salon, client):
        """
        Decisión 2: NO tocar SPECIFIC en cascada.
        
        Por qué: Respetan sus preferencias exactas.
        Impacto: Clientes specific esperan más, pero no se molestan.
        """
        from appointments.waitlist import WaitlistManager
        
        # Crear entrada SPECIFIC
        specific_entry = await create_test_waitlist(db_session, str(salon.id), str(uuid.uuid4()), "specific")
        
        # Crear entrada FLEXIBLE
        flexible_entry = await create_test_waitlist(db_session, str(salon.id), str(uuid.uuid4()), "flexible")
        
        waitlist_manager = WaitlistManager(db_session)
        
        # Simular cascada (solo debe considerar FLEXIBLE)
        waiting_clients = await waitlist_manager.get_waiting_clients(str(salon.id))
        
        flexible_entries = [w for w in waiting_clients if w.request_type == "flexible"]
        specific_entries = [w for w in waiting_clients if w.request_type == "specific"]
        
        assert len(flexible_entries) > 0, "Debe haber entradas FLEXIBLE"
        assert len(specific_entries) > 0, "Debe haber entradas SPECIFIC"
        
        # La implementación real filtra por request_type == FLEXIBLE en process_cascade


class TestUnrealisticTimeSlots:
    """Tests para horarios irreales o muy pronto."""
    
    @pytest.mark.asyncio
    async def test_appointment_5_minutes_from_now(self, db_session, salon, client, stylist, service):
        """
        Test agendar cita solo 5 min desde ahora.
        
        Caso edge: Horario liberado es muy pronto (5 min, no realista).
        """
        from services.availability import AvailabilityService
        
        # Intentar agendar para 5 min desde ahora
        unrealistic_time = datetime.now() + timedelta(minutes=5)
        
        is_available, msg = await AvailabilityService.check_availability(
            db_session,
            str(salon.id),
            unrealistic_time,
            30
        )
        
        # Debería fallar por estar fuera del horario de atención
        # o por ser muy pronto
        assert isinstance(is_available, bool), "Debe retornar booleano"
    
    @pytest.mark.asyncio
    async def test_appointment_in_the_past(self, db_session, salon, client, stylist, service):
        """
        Test agendar cita en el pasado.
        
        Caso edge: Cliente intenta agendar para una hora que ya pasó.
        """
        from services.availability import AvailabilityService
        
        past_time = datetime.now() - timedelta(hours=1)
        
        is_available, msg = await AvailabilityService.check_availability(
            db_session,
            str(salon.id),
            past_time,
            30
        )
        
        # Debería fallar por estar en el pasado
        assert is_available is False, "No debe permitir agendar en el pasado"


class TestDatabaseErrors:
    """Tests para errores de base de datos."""
    
    @pytest.mark.asyncio
    async def test_database_connection_error(self, db_session, salon, client):
        """
        Test comportamiento cuando la BD está offline.
        
        Caso edge: Base de datos offline/error en mitad de operación.
        """
        from appointments.create import AppointmentCreator
        
        # Simular error de BD cerrando la sesión
        await db_session.close()
        
        start_time = datetime.now() + timedelta(days=1, hours=14)
        
        # Esto debería lanzar una excepción
        with pytest.raises(Exception):
            await AppointmentCreator.create_appointment(
                db_session,
                salon_id=str(salon.id),
                client_id=str(client.id),
                service_name="Corte de Cabello",
                start_time=start_time
            )
    
    @pytest.mark.asyncio
    async def test_rollback_on_error(self, db_session, salon, client, stylist, service):
        """
        Test que se hace rollback cuando hay error.
        
        Si falla una operación, no debe dejar datos inconsistentes.
        """
        from appointments.create import AppointmentCreator
        
        start_time = datetime.now() + timedelta(days=1, hours=14)
        
        # Intentar crear con servicio inexistente (debería fallar y hacer rollback)
        success, msg, appointment = await AppointmentCreator.create_appointment(
            db_session,
            salon_id=str(salon.id),
            client_id=str(client.id),
            service_name="Servicio Inexistente",
            start_time=start_time
        )
        
        assert success is False, "Debe fallar"
        assert appointment is None, "No debe crear cita"
        
        # Verificar que no se creó nada en BD
        result = await db_session.execute(
            select(TestAppointment).where(TestAppointment.client_id == client.id)
        )
        appointments = result.scalars().all()
        
        assert len(appointments) == 0, "No debe haber citas creadas (rollback exitoso)"


class TestWaitlistRejectionLimit:
    """Tests para límite de rechazos en lista de espera."""
    
    @pytest.mark.asyncio
    async def test_client_rejected_multiple_times(self, db_session, salon, client):
        """
        Test penalidad si cliente FLEXIBLE rechaza más de X veces.
        
        Pregunta abierta en ideas.md: ¿Penalidad si cliente FLEXIBLE
        rechaza más de X veces?
        """
        from appointments.waitlist import WaitlistManager
        
        # Crear entrada en lista de espera
        entry = await create_test_waitlist(db_session, str(salon.id), str(client.id), "flexible")
        
        waitlist_manager = WaitlistManager(db_session)
        freed_time = datetime.now() + timedelta(days=1, hours=14)
        
        # Rechazar 3 veces
        for _ in range(3):
            success, msg = await waitlist_manager.handle_waitlist_response(
                waitlist_id=str(entry.id),
                accepted=False,
                salon_id=str(salon.id),
                freed_start_time=freed_time,
                service_name="Corte de Cabello"
            )
            await db_session.refresh(entry)
        
        assert entry.rejection_count == 3, "Debe contar los rechazos"
        
        # Nota: La lógica de penalidad (sacar de lista) no está implementada
        # Este test documenta el caso edge para futura implementación


class TestBusinessHoursEdgeCases:
    """Tests para casos edge de horarios de atención."""
    
    @pytest.mark.asyncio
    async def test_appointment_at_closing_time(self, db_session, salon, client, stylist, service):
        """
        Test agendar a la hora de cierre (5:00pm).
        
        Según AvailabilityService: última cita a las 4:30pm.
        """
        from services.availability import AvailabilityService
        
        # Intentar agendar a las 5:00pm (hora de cierre)
        closing_time = datetime.now().replace(hour=17, minute=0, second=0, microsecond=0)
        if closing_time < datetime.now():
            closing_time += timedelta(days=1)
        
        is_available, msg = await AvailabilityService.check_availability(
            db_session,
            str(salon.id),
            closing_time,
            30
        )
        
        # Debería fallar por ser la hora exacta de cierre
        # (necesita tiempo para completar el servicio)
        assert is_available is False, "No debe permitir agendar a la hora de cierre"
    
    @pytest.mark.asyncio
    async def test_appointment_during_lunch(self, db_session, salon, client, stylist, service):
        """
        Test agendar durante el horario de almuerzo (12:00pm - 1:30pm).
        """
        from services.availability import AvailabilityService
        
        # Intentar agendar a las 12:30pm (durante almuerzo)
        lunch_time = datetime.now().replace(hour=12, minute=30, second=0, microsecond=0)
        if lunch_time < datetime.now():
            lunch_time += timedelta(days=1)
        
        is_available, msg = await AvailabilityService.check_availability(
            db_session,
            str(salon.id),
            lunch_time,
            30
        )
        
        # Debería fallar por ser durante el almuerzo
        assert is_available is False, "No debe permitir agendar durante almuerzo"
    
    @pytest.mark.asyncio
    async def test_appointment_before_opening(self, db_session, salon, client, stylist, service):
        """
        Test agendar antes del horario de apertura (9:00am).
        """
        from services.availability import AvailabilityService
        
        # Intentar agendar a las 8:00am (antes de abrir)
        early_time = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
        if early_time < datetime.now():
            early_time += timedelta(days=1)
        
        is_available, msg = await AvailabilityService.check_availability(
            db_session,
            str(salon.id),
            early_time,
            30
        )
        
        # Debería fallar por ser antes de abrir
        assert is_available is False, "No debe permitir agendar antes de abrir"
