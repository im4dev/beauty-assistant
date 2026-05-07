"""
Scheduler para envío automático de recordatorios de citas.

Este módulo ejecuta tareas periódicas para enviar recordatorios
a clientes 24 horas y 1 hora antes de sus citas.
"""
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import Appointment, AppointmentStatus, Client, Salon
from notifications.sender import NotificationSender
import asyncio
import logging

logger = logging.getLogger(__name__)


class ReminderScheduler:
    """Scheduler para envío de recordatorios automáticos"""
    
    def __init__(self, db_session_factory):
        """
        Args:
            db_session_factory: Factory para crear sesiones de DB
        """
        self.db_session_factory = db_session_factory
        self.notification_sender = NotificationSender()
    
    async def check_and_send_reminders(self):
        """
        Busca citas que requieren recordatorio y los envía.
        
        Se ejecuta periódicamente (recomendado: cada 5-10 minutos)
        """
        async with self.db_session_factory() as db:
            now = datetime.utcnow()
            
            # 1. Recordatorios de 24 horas
            await self._send_24h_reminders(db, now)
            
            # 2. Recordatorios de 1 hora
            await self._send_1h_reminders(db, now)
    
    async def _send_24h_reminders(self, db: AsyncSession, now: datetime):
        """
        Envía recordatorios 24 horas antes de la cita.
        
        Busca citas que:
        - Están SCHEDULED
        - Son en aproximadamente 24 horas (entre 23h y 25h desde ahora)
        - No tienen recordatorio de 24h enviado
        """
        reminder_window_start = now + timedelta(hours=23)
        reminder_window_end = now + timedelta(hours=25)
        
        query = select(Appointment).where(
            Appointment.status == AppointmentStatus.SCHEDULED,
            Appointment.start_time >= reminder_window_start,
            Appointment.start_time <= reminder_window_end,
            Appointment.reminder_24h_sent == False  # Necesitamos agregar este campo al modelo  # Necesitamos agregar este campo al modelo  # Necesitamos agregar este campo al modelo
        )
        
        result = await db.execute(query)
        appointments = result.scalars().all()
        
        for appointment in appointments:
            try:
                # Obtener cliente y salón
                client = await db.get(Client, appointment.client_id)
                salon = await db.get(Salon, appointment.salon_id)
                
                if not client or not salon:
                    continue
                
                # Calcular hora local del salón
                import zoneinfo
                salon_tz = zoneinfo.ZoneInfo(salon.timezone if salon.timezone else "UTC")
                local_time = appointment.start_time.astimezone(salon_tz)
                
                # Enviar recordatorio
                success = await self.notification_sender.send_to_client(
                    client.wa_id,
                    f"📅 Recordatorio de cita\n\n"
                    f"Hola {client.name}, te recordamos que tienes una cita "
                    f"mañana a las {local_time.strftime('%H:%M')} para {appointment.service_name}.\n\n"
                    f"¡Te esperamos!"
                )
                
                if success:
                    appointment.reminder_24h_sent = True
                    await db.commit()
                    logger.info(f"Recordatorio 24h enviado para cita {appointment.id}")
                
            except Exception as e:
                logger.error(f"Error enviando recordatorio 24h para cita {appointment.id}: {e}")
    
    async def _send_1h_reminders(self, db: AsyncSession, now: datetime):
        """
        Envía recordatorios 1 hora antes de la cita.
        
        Busca citas que:
        - Están SCHEDULED
        - Son en aproximadamente 1 hora (entre 50min y 70min desde ahora)
        - No tienen recordatorio de 1h enviado
        """
        reminder_window_start = now + timedelta(minutes=50)
        reminder_window_end = now + timedelta(minutes=70)
        
        query = select(Appointment).where(
            Appointment.status == AppointmentStatus.SCHEDULED,
            Appointment.start_time >= reminder_window_start,
            Appointment.start_time <= reminder_window_end,
            Appointment.reminder_1h_sent == False  # Necesitamos agregar este campo al modelo
        )
        
        result = await db.execute(query)
        appointments = result.scalars().all()
        
        for appointment in appointments:
            try:
                # Obtener cliente y salón
                client = await db.get(Client, appointment.client_id)
                salon = await db.get(Salon, appointment.salon_id)
                
                if not client or not salon:
                    continue
                
                # Calcular hora local del salón
                import zoneinfo
                salon_tz = zoneinfo.ZoneInfo(salon.timezone if salon.timezone else "UTC")
                local_time = appointment.start_time.astimezone(salon_tz)
                
                # Enviar recordatorio
                success = await self.notification_sender.send_to_client(
                    client.wa_id,
                    f"⏰ Tu cita es en 1 hora\n\n"
                    f"Hola {client.name}, te recordamos que tu cita "
                    f"es a las {local_time.strftime('%H:%M')} para {appointment.service_name}.\n\n"
                    f"¡Por favor llega puntual!"
                )
                
                if success:
                    appointment.reminder_1h_sent = True
                    await db.commit()
                    logger.info(f"Recordatorio 1h enviado para cita {appointment.id}")
                
            except Exception as e:
                logger.error(f"Error enviando recordatorio 1h para cita {appointment.id}: {e}")
    
    async def start_background_task(self, interval_minutes: int = 5):
        """
        Inicia la tarea de fondo que ejecuta el scheduler periódicamente.
        
        Args:
            interval_minutes: Intervalo en minutos entre ejecuciones
        """
        logger.info(f"Iniciando scheduler de recordatorios (intervalo: {interval_minutes} min)")
        
        while True:
            try:
                await self.check_and_send_reminders()
                await asyncio.sleep(interval_minutes * 60)
            except Exception as e:
                logger.error(f"Error en scheduler: {e}")
                await asyncio.sleep(60)  # Esperar 1 min antes de reintentar
