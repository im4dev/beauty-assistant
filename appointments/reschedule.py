from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import Appointment, AppointmentStatus, Service, Salon, Stylist, Client
from services.availability import AvailabilityService
from notifications.sender import NotificationSender
from appointments.waitlist import WaitlistManager
import zoneinfo


class AppointmentRescheduler:
    """Lógica para reagendar citas existentes"""
    
    @classmethod
    async def reschedule_appointment(
        cls,
        db: AsyncSession,
        appointment: Appointment,
        new_start_time: datetime,
        service_name: str = None,
        is_flexible: bool = None
    ) -> tuple[bool, str]:
        """
        Reagenda una cita existente a un nuevo horario.
        
        Args:
            db: Sesión de base de datos
            appointment: Objeto Appointment existente
            new_start_time: Nueva fecha/hora de inicio
            service_name: Nuevo nombre de servicio (opcional)
            is_flexible: Flag de flexibilidad (opcional)
        
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
            
        if is_flexible is not None:
            appointment.is_flexible = is_flexible
        
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
                print(f"DEBUG: Enviando notificación de reprogramación al estilista {stylist_obj.name} ({stylist_obj.phone_number})")
                await notification_sender.notify_stylist_appointment_rescheduled(
                    phone_number=stylist_obj.phone_number,
                    client_name=client_obj.name or "Cliente",
                    old_date_time=old_local.strftime("%d/%m a las %H:%M"),
                    new_date_time=new_local.strftime("%d/%m a las %H:%M")
                )
            else:
                print(f"DEBUG: No se notificó al estilista en reprogramación. Objeto encontrado: {bool(stylist_obj)}, Teléfono: {stylist_obj.phone_number if stylist_obj else 'N/A'}")
        except Exception as e:
            print(f"❌ Error notificando al estilista en reprogramación: {e}")
        
        # 2. Iniciar cascada para llenar el hueco que acabamos de liberar (old_time)
        try:
            waitlist_manager = WaitlistManager(db)
            # El hueco liberado es old_time, con la duración original (que asumimos es la misma)
            duration = (appointment.end_time - appointment.start_time).total_seconds() / 60
            await waitlist_manager.process_cascade(
                salon_id=appointment.salon_id,
                freed_start_time=old_time,
                freed_duration=int(duration),
                service_name=appointment.service_name,
                stylist_id=appointment.stylist_id
            )
        except Exception as e:
            print(f"Error en cascada tras reprogramación: {e}")

        return True, f"Cita reprogramada de {old_local.strftime('%d/%m %H:%M')} a {new_local.strftime('%d/%m %H:%M')}."
