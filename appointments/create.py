from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import Appointment, AppointmentStatus, Client, Stylist, Service, Salon
from services.availability import AvailabilityService
from notifications.sender import NotificationSender
import zoneinfo


class AppointmentCreator:
    """Lógica para crear nuevas citas"""
    
    @staticmethod
    async def create_appointment(
        db: AsyncSession,
        salon_id: str,
        client_id: str,
        service_name: str,
        start_time: datetime,
        stylist_id: str = None,
        is_flexible: bool = False
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
        service = service_res.scalars().first()
        
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
        
        # 3. Asignar estilista (si no se especificó, buscar uno libre)
        if not stylist_id:
            # Buscar TODOS los estilistas activos del salón
            stylists_res = await db.execute(
                select(Stylist).where(
                    Stylist.salon_id == salon_id,
                    Stylist.is_active == True
                )
            )
            stylists = stylists_res.scalars().all()
            
            if not stylists:
                return False, "No hay estilistas activos en este salón.", None
            
            # Buscar cuál de ellos está libre en este horario
            for s in stylists:
                overlap_query = select(Appointment).where(
                    Appointment.stylist_id == s.id,
                    Appointment.status == AppointmentStatus.SCHEDULED,
                    Appointment.start_time < end_time,
                    Appointment.end_time > start_time
                )
                overlap_res = await db.execute(overlap_query)
                if not overlap_res.scalars().first():
                    stylist_id = s.id
                    break
            
            if not stylist_id:
                return False, "Lo sentimos, todos nuestros estilistas están ocupados en ese horario.", None
        
        # 4. Crear la cita
        new_appointment = Appointment(
            salon_id=salon_id,
            client_id=client_id,
            stylist_id=stylist_id,
            service_id=service.id,
            service_name=service_name,
            start_time=start_time,
            end_time=end_time,
            status=AppointmentStatus.SCHEDULED,
            is_flexible=is_flexible
        )
        
        db.add(new_appointment)
        await db.commit()
        await db.refresh(new_appointment)

        # 5. Notificar al estilista (background task o directo)
        try:
            notification_sender = NotificationSender()
            # Cargar datos necesarios para la notificación
            stylist_obj = await db.get(Stylist, stylist_id)
            client_obj = await db.get(Client, client_id)
            salon_obj = await db.get(Salon, salon_id)
            
            if stylist_obj and stylist_obj.phone_number:
                tz = zoneinfo.ZoneInfo(salon_obj.timezone if salon_obj and salon_obj.timezone else "UTC")
                local_time = start_time.astimezone(tz)
                formatted_time = local_time.strftime("%d/%m a las %H:%M")
                
                print(f"DEBUG: Enviando notificación de nueva cita al estilista {stylist_obj.name} ({stylist_obj.phone_number})")
                await notification_sender.notify_stylist_new_appointment(
                    phone_number=stylist_obj.phone_number,
                    client_name=client_obj.name or "Cliente",
                    service_name=service_name,
                    date_time=formatted_time
                )
            else:
                print(f"DEBUG: No se notificó al estilista en creación. Objeto encontrado: {bool(stylist_obj)}, Teléfono: {stylist_obj.phone_number if stylist_obj else 'N/A'}")
        except Exception as e:
            print(f"❌ Error notificando al estilista en creación: {e}")
        
        return True, "Cita creada exitosamente.", new_appointment
