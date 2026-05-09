from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import Appointment, AppointmentStatus, Stylist, Client, Salon
from appointments.waitlist import WaitlistManager
from notifications.sender import NotificationSender
import zoneinfo


class AppointmentCanceller:
    """Lógica para cancelar citas y gestionar lista de espera"""
    
    @staticmethod
    async def cancel_appointment(
        db: AsyncSession,
        appointment: Appointment,
        trigger_waitlist: bool = True
    ) -> tuple[bool, str]:
        """
        Cancela una cita y opcionalmente inicia cascada de lista de espera.
        
        Args:
            db: Sesión de base de datos
            appointment: Objeto Appointment a cancelar
            trigger_waitlist: Si es True, inicia cascada de lista de espera
        
        Returns:
            (success, message)
        """
        salon_id = str(appointment.salon_id)
        freed_time = appointment.start_time
        freed_duration = (appointment.end_time - freed_time).total_seconds() / 60
        
        # 1. Marcar como cancelada
        appointment.status = AppointmentStatus.CANCELLED
        await db.commit()

        # Notificar al estilista
        try:
            notification_sender = NotificationSender()
            # Cargar datos necesarios
            stylist_obj = await db.get(Stylist, appointment.stylist_id)
            client_obj = await db.get(Client, appointment.client_id)
            salon_obj = await db.get(Salon, appointment.salon_id)
            
            if stylist_obj and stylist_obj.phone_number:
                tz = zoneinfo.ZoneInfo(salon_obj.timezone if salon_obj and salon_obj.timezone else "UTC")
                local_time = appointment.start_time.astimezone(tz)
                formatted_time = local_time.strftime("%d/%m a las %H:%M")
                
                await notification_sender.notify_stylist_appointment_cancelled(
                    phone_number=stylist_obj.phone_number,
                    client_name=client_obj.name or "Cliente",
                    date_time=formatted_time
                )
        except Exception as e:
            print(f"Error notificando al estilista en cancelación: {e}")
        
        # 2. Iniciar cascada de lista de espera si se solicita
        if trigger_waitlist:
            waitlist_manager = WaitlistManager(db)
            booked_client = await waitlist_manager.process_cascade(
                salon_id=salon_id,
                freed_start_time=freed_time,
                freed_duration=int(freed_duration),
                service_name=appointment.service_name,
                stylist_id=str(appointment.stylist_id)
            )
            
            if booked_client:
                return True, f"Cita cancelada. El horario fue asignado automáticamente a un cliente en lista de espera."
        
        return True, "Cita cancelada exitosamente."
