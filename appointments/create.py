from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import Appointment, AppointmentStatus, Client, Stylist, Service
from services.availability import AvailabilityService


class AppointmentCreator:
    """Lógica para crear nuevas citas"""
    
    @staticmethod
    async def create_appointment(
        db: AsyncSession,
        salon_id: str,
        client_id: str,
        service_name: str,
        start_time: datetime,
        stylist_id: str = None
    ) -> tuple[bool, str, Appointment | None]:
        """
        Crea una nueva cita validando disponibilidad.
        
        Returns:
            (success, message, appointment)
        """
        # 1. Obtener el servicio para determinar duración
        service_res = await db.execute(
            select(Service).where(Service.name == service_name, Service.salon_id == salon_id)
        )
        service = service_res.scalar_one_or_none()
        
        if not service:
            return False, f"Servicio '{service_name}' no encontrado.", None
        
        duration = service.duration_minutes
        end_time = start_time + timedelta(minutes=duration)
        
        # 2. Validar disponibilidad
        is_available, msg = await AvailabilityService.check_availability(
            db, salon_id, start_time, duration
        )
        
        if not is_available:
            return False, msg, None
        
        # 3. Asignar estilista (si no se especificó, usar uno por defecto)
        if not stylist_id:
            # Buscar estilista activo del salón
            stylist_res = await db.execute(
                select(Stylist).where(
                    Stylist.salon_id == salon_id,
                    Stylist.is_active == True
                ).limit(1)
            )
            stylist = stylist_res.scalar_one_or_none()
            if not stylist:
                return False, "No hay estilistas disponibles en este momento.", None
            stylist_id = stylist.id
        
        # 4. Crear la cita
        new_appointment = Appointment(
            salon_id=salon_id,
            client_id=client_id,
            stylist_id=stylist_id,
            service_id=service.id,
            service_name=service_name,
            start_time=start_time,
            end_time=end_time,
            status=AppointmentStatus.SCHEDULED
        )
        
        db.add(new_appointment)
        await db.commit()
        await db.refresh(new_appointment)
        
        return True, "Cita creada exitosamente.", new_appointment
