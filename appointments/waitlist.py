from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from db.models import (
    Waitlist, WaitlistRequestType, WaitlistStatus,
    Appointment, AppointmentStatus, Client, Stylist, Service
)
from appointments.create import AppointmentCreator


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
        """Agrega un cliente a la lista de espera"""
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
        
        Proceso:
        1. Buscar lista de espera FLEXIBLE (último → primero)
        2. Ofrecer horario al último flexible
        3. Esperar 5 min (timeout) - implementado con status 'offered'
        4. Si acepta → agendar, fin
        5. Si rechaza → siguiente cliente
        6. Si nadie → retornar None
        
        Returns:
            Client que fue agendado, o None si nadie aceptó
        """
        # 1. Buscar lista de espera FLEXIBLE, ordenada inversamente por created_at
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
        
        for entry in waitlist_entries:
            # 2. Marcar como 'offered' para evitar que otros procesos lo agarren
            entry.status = WaitlistStatus.OFFERED
            entry.updated_at = datetime.utcnow()
            await self.db.commit()
            
            # 3. Obtener datos del cliente
            client_res = await self.db.execute(
                select(Client).where(Client.id == entry.client_id)
            )
            client = client_res.scalar_one_or_none()
            
            if not client:
                continue
            
            # 4. Aquí se debería enviar mensaje por WhatsApp al cliente
            # "¿Disponible para [servicio] a las [hora] con [estilista]?"
            # El cliente responde y se procesa la respuesta
            
            # Por ahora, simulamos que el cliente NO responde
            # En producción, esto debería ser manejado por un endpoint webhook
            # que procese la respuesta del cliente
            
            # Simulación: si nadie responde en 5 min, pasamos al siguiente
            await self._handle_no_response(entry)
            
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
