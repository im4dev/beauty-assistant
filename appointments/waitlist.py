from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from db.models import (
    Waitlist, WaitlistRequestType, WaitlistStatus,
    Appointment, AppointmentStatus, Client, Stylist, Service, Salon, SessionState
)
from appointments.create import AppointmentCreator
from core.session import SessionManager
from notifications.sender import NotificationSender
import json
import zoneinfo


class WaitlistManager:
    """Gestiona la lista de espera y la cascada inversa"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def add_to_waitlist(
        self,
        salon_id: str,
        client_id: str,
        request_type: WaitlistRequestType,
        preferred_date: datetime = None,
        preferred_time: str = None,
        preferred_stylist_id: str = None,
        preferred_service_id: str = None
    ) -> Waitlist:
        """Agrega un cliente a la lista de espera (sin duplicar si ya está esperando)"""
        existing = await self.db.execute(
            select(Waitlist).where(
                Waitlist.salon_id == salon_id,
                Waitlist.client_id == client_id,
                Waitlist.request_type == request_type,
                Waitlist.preferred_service_id == preferred_service_id,
                Waitlist.status == WaitlistStatus.WAITING
            )
        )
        existing_entry = existing.scalars().first()
        if existing_entry:
            return existing_entry

        waitlist_entry = Waitlist(
            salon_id=salon_id,
            client_id=client_id,
            request_type=request_type,
            preferred_date=preferred_date,
            preferred_time=preferred_time,
            preferred_stylist_id=preferred_stylist_id,
            preferred_service_id=preferred_service_id,
            status=WaitlistStatus.WAITING
        )
        
        self.db.add(waitlist_entry)
        await self.db.commit()
        await self.db.refresh(waitlist_entry)
        
        return waitlist_entry
    
    async def process_cascade(
        self,
        salon_id: str,
        freed_start_time: datetime,
        freed_duration: int,
        service_name: str = None,
        stylist_id: str = None
    ) -> Client | None:
        """
        Ejecuta cascada inversa de lista de espera.
        """
        # 0. Obtener datos del salón para el timezone
        salon_res = await self.db.execute(select(Salon).where(Salon.id == salon_id))
        salon = salon_res.scalar_one_or_none()
        tz_str = salon.timezone if salon and salon.timezone else "UTC"
        tz = zoneinfo.ZoneInfo(tz_str)
        
        # Formatear la fecha para el mensaje
        local_time = freed_start_time.astimezone(tz)
        formatted_time = local_time.strftime("%d/%m a las %H:%M")

        # Obtener nombre del estilista
        stylist_name = None
        if stylist_id:
            stylist_res = await self.db.execute(select(Stylist).where(Stylist.id == stylist_id))
            stylist = stylist_res.scalar_one_or_none()
            if stylist:
                stylist_name = stylist.name

        # --- NUEVA LÓGICA: Buscar candidatos para ADELANTAR CITA ---
        # Buscamos citas agendadas para el mismo día, mismo estilista, que sean 'is_flexible' y empiecen DESPUÉS del hueco liberado
        from datetime import time
        day_start = datetime.combine(freed_start_time.date(), time.min).replace(tzinfo=freed_start_time.tzinfo)
        day_end = datetime.combine(freed_start_time.date(), time.max).replace(tzinfo=freed_start_time.tzinfo)

        move_up_query = select(Appointment).where(
            Appointment.salon_id == salon_id,
            Appointment.stylist_id == stylist_id,
            Appointment.status == AppointmentStatus.SCHEDULED,
            Appointment.is_flexible == True,
            Appointment.start_time > freed_start_time,
            Appointment.start_time <= day_end
        ).order_by(Appointment.start_time.asc())

        move_up_res = await self.db.execute(move_up_query)
        move_up_candidates = move_up_res.scalars().all()

        notification_sender = NotificationSender()

        for appt in move_up_candidates:
            # Notificar al cliente si tiene sesión activa o podemos crearla
            client_res = await self.db.execute(select(Client).where(Client.id == appt.client_id))
            client = client_res.scalar_one_or_none()
            if not client: continue

            session_manager = SessionManager(self.db)
            session = await session_manager.get_or_create(client.wa_id, salon_id)
            
            # Formatear hora de su cita actual
            current_time = appt.start_time.astimezone(tz).strftime("%H:%M")
            
            # Enviar notificación de adelanto
            message = (
                f"¡Hola {client.name}! 👋 Se liberó un espacio más temprano hoy con {stylist_name or 'tu estilista'} "
                f"a las {formatted_time.split(' a las ')[1]}.\n\n"
                f"Actualmente tienes cita a las {current_time}. ¿Te gustaría adelantarla para las {formatted_time.split(' a las ')[1]}?\n\n"
                f"Responde *sí* para moverla o ignora este mensaje si prefieres tu horario actual."
            )
            
            success = await notification_sender.send_to_client(client.wa_id, message)
            
            if success:
                session.current_step = "CONFIRMING_WAITLIST"
                session.context_data = json.dumps({
                    "offered_slot": freed_start_time.isoformat(),
                    "service": appt.service_name,
                    "stylist_id": str(stylist_id),
                    "move_up_appointment_id": str(appt.id),
                    "is_move_up": True
                })
                await self.db.commit()
                print(f"DEBUG: Preguntando a {client.name} con el numero {client.wa_id} si desea reagendar")
                # Por ahora, solo ofrecemos al primero disponible para no saturar
                return client

        # 1. Si no hubo adelantos, buscar lista de espera FLEXIBLE
        result = await self.db.execute(
            select(Waitlist)
            .where(
                Waitlist.salon_id == salon_id,
                Waitlist.request_type == WaitlistRequestType.FLEXIBLE,
                Waitlist.status == WaitlistStatus.WAITING
            )
            .order_by(Waitlist.created_at.desc())
        )
        waitlist_entries = result.scalars().all()
        
        notification_sender = NotificationSender()
        
        for entry in waitlist_entries:
            # 2. Marcar como 'offered'
            entry.status = WaitlistStatus.OFFERED
            entry.is_notified = True
            entry.updated_at = datetime.utcnow()
            
            # 3. Obtener datos del cliente
            client_res = await self.db.execute(
                select(Client).where(Client.id == entry.client_id)
            )
            client = client_res.scalar_one_or_none()
            
            if not client:
                continue
            
            # 4. Actualizar el estado de la sesión del cliente
            # Esto permitirá que el Orchestrator sepa qué está confirmando el cliente
            session_res = await self.db.execute(
                select(SessionState).where(SessionState.wa_id == client.wa_id)
            )
            session = session_res.scalar_one_or_none()
            
            if not session:
                session = SessionState(wa_id=client.wa_id, salon_id=salon_id)
                self.db.add(session)
            
            session.current_step = "CONFIRMING_WAITLIST"
            session.context_data = json.dumps({
                "offered_slot": freed_start_time.isoformat(),
                "service": service_name,
                "stylist_id": stylist_id,
                "waitlist_id": str(entry.id)
            })
            
            await self.db.commit()
            
            # 5. Enviar mensaje por WhatsApp
            print(f"DEBUG: Enviando oferta de lista de espera a {client.wa_id}")
            await notification_sender.notify_waitlist_offer(
                phone_number=client.wa_id,
                service_name=service_name or "tu servicio",
                date_time=formatted_time,
                stylist_name=stylist_name
            )
            
        return None
    
    async def handle_waitlist_response(
        self,
        waitlist_id: str,
        accepted: bool,
        salon_id: str,
        freed_start_time: datetime,
        service_name: str
    ) -> tuple[bool, str]:
        """
        Procesa la respuesta de un cliente de la lista de espera.
        
        Args:
            waitlist_id: ID de la entrada en waitlist
            accepted: True si el cliente aceptó, False si rechazó
            salon_id: ID del salón
            freed_start_time: Horario liberado
            service_name: Nombre del servicio
        
        Returns:
            (success, message)
        """
        result = await self.db.execute(
            select(Waitlist).where(Waitlist.id == waitlist_id)
        )
        entry = result.scalar_one_or_none()
        
        if not entry:
            return False, "Entrada de lista de espera no encontrada."
        
        if accepted:
            # Cliente aceptó: crear la cita
            success, msg, appointment = await AppointmentCreator.create_appointment(
                self.db,
                salon_id=salon_id,
                client_id=str(entry.client_id),
                service_name=service_name,
                start_time=freed_start_time
            )
            
            if success:
                entry.status = WaitlistStatus.WAITING  # Ya fue agendado, resetear estado
                await self.db.commit()
                return True, "Cita agendada exitosamente desde lista de espera."
            else:
                entry.status = WaitlistStatus.WAITING
                await self.db.commit()
                return False, f"No se pudo agendar: {msg}"
        else:
            # Cliente rechazó
            entry.status = WaitlistStatus.REJECTED
            entry.rejection_count += 1
            entry.updated_at = datetime.utcnow()
            
            # Si ha rechazado muchas veces, podría ser penalizado
            if entry.rejection_count >= 3:
                entry.status = WaitlistStatus.NO_RESPONSE  # O algún otro estado
            
            await self.db.commit()
            return True, "Respuesta registrada. Buscando siguiente cliente en lista de espera."
    
    async def _handle_no_response(self, entry: Waitlist):
        """Marca una entrada como no respondida después del timeout"""
        entry.status = WaitlistStatus.NO_RESPONSE
        entry.updated_at = datetime.utcnow()
        await self.db.commit()
    
    async def get_waiting_clients(self, salon_id: str) -> list[Waitlist]:
        """Obtiene todos los clientes en lista de espera de un salón"""
        result = await self.db.execute(
            select(Waitlist)
            .where(
                Waitlist.salon_id == salon_id,
                Waitlist.status == WaitlistStatus.WAITING
            )
            .order_by(Waitlist.created_at.asc())
        )
        return result.scalars().all()
