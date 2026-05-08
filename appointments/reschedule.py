from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import Appointment, AppointmentStatus, Service, Salon
from services.availability import AvailabilityService


class AppointmentRescheduler:
    """Lógica para reagendar citas existentes"""
    
    @staticmethod
    async def reschedule_appointment(
        db: AsyncSession,
        appointment: Appointment,
        new_start_time: datetime,
        service_name: str = None
    ) -> tuple[bool, str]:
        """
        Reagenda una cita existente a un nuevo horario.
        
        Args:
            db: Sesión de base de datos
            appointment: Objeto Appointment existente
            new_start_time: Nueva fecha/hora de inicio
            service_name: Nuevo nombre de servicio (opcional)
        
        Returns:
            (success, message)
        """
        # 1. Determinar duración del servicio
        duration = 30  # Default
        if service_name:
            service_res = await db.execute(
                select(Service).where(
                    Service.name == service_name,
                    Service.salon_id == appointment.salon_id
                )
            )
            service = service_res.scalars().first()
            if service:
                duration = service.duration_minutes
        elif appointment.service_id:
            duration = appointment.service.duration_minutes
        
        new_end_time = new_start_time + timedelta(minutes=duration)
        
        # 2. Validar disponibilidad del nuevo horario (excluyendo la cita actual)
        is_available, msg = await AvailabilityService.check_availability(
            db,
            str(appointment.salon_id),
            new_start_time,
            duration,
            exclude_appointment_id=appointment.id
        )
        
        if not is_available:
            return False, msg
        
        # 3. Actualizar la cita
        old_time = appointment.start_time
        appointment.start_time = new_start_time
        appointment.end_time = new_end_time
        
        if service_name:
            appointment.service_name = service_name
        
        await db.commit()

        import zoneinfo
        salon_res = await db.execute(select(Salon).where(Salon.id == appointment.salon_id))
        salon_obj = salon_res.scalars().first()
        salon_tz = zoneinfo.ZoneInfo(salon_obj.timezone if salon_obj and salon_obj.timezone else 'UTC')
        
        old_local = old_time.astimezone(salon_tz)
        new_local = new_start_time.astimezone(salon_tz)
        
        return True, f"Cita reprogramada de {old_local.strftime('%d/%m %H:%M')} a {new_local.strftime('%d/%m %H:%M')}."
