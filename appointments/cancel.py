from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import Appointment, AppointmentStatus
from appointments.waitlist import WaitlistManager


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
