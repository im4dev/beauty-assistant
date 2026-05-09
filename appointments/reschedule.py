from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import Appointment, AppointmentStatus, Service, Salon, Stylist, Client
from services.availability import AvailabilityService
from notifications.sender import NotificationSender
import zoneinfo


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
        
        # Notificar al estilista
        try:
            notification_sender = NotificationSender()
            stylist_obj = await db.get(Stylist, appointment.stylist_id)
            client_obj = await db.get(Client, appointment.client_id)
            
            if stylist_obj and stylist_obj.phone_number:
                await notification_sender.notify_stylist_appointment_rescheduled(
                    phone_number=stylist_obj.phone_number,
                    client_name=client_obj.name or "Cliente",
                    old_date_time=old_local.strftime("%d/%m a las %H:%M"),
                    new_date_time=new_local.strftime("%d/%m a las %H:%M")
                )
        except Exception as e:
            print(f"Error notificando al estilista en reprogramación: {e}")
        
        return True, f"Cita reprogramada de {old_local.strftime('%d/%m %H:%M')} a {new_local.strftime('%d/%m %H:%M')}."
