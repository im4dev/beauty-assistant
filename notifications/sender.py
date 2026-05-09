from services.whatsapp_client import WhatsAppClient


class NotificationSender:
    """Envía notificaciones por WhatsApp"""
    
    def __init__(self):
        self.wa_client = WhatsAppClient()
    
    async def send_to_client(self, phone_number: str, message: str) -> bool:
        """
        Envía un mensaje a un cliente por WhatsApp.
        
        Args:
            phone_number: Número de teléfono del cliente
            message: Mensaje a enviar
        
        Returns:
            True si se envió exitosamente, False en caso contrario
        """
        try:
            await self.wa_client.send_text_message(phone_number, message)
            return True
        except Exception as e:
            print(f"Error enviando mensaje a {phone_number}: {e}")
            return False
    
    async def notify_waitlist_offer(
        self,
        phone_number: str,
        service_name: str,
        date_time: str,
        stylist_name: str = None
    ) -> bool:
        """
        Notifica a un cliente en lista de espera sobre un horario disponible.
        
        Args:
            phone_number: Número del cliente
            service_name: Nombre del servicio
            date_time: Fecha y hora formateada
            stylist_name: Nombre del estilista (opcional)
        
        Returns:
            True si se envió exitosamente
        """
        stylist_text = f" con {stylist_name}" if stylist_name else ""
        message = (
            f"¡Buenas noticias! 🎉\n\n"
            f"Se liberó un horario para {service_name}{stylist_text} "
            f"el {date_time}.\n\n"
            f"¿Te interesa agendarlo? Responde 'sí' para confirmar o 'no' para pasar."
        )
        
        return await self.send_to_client(phone_number, message)
    
    async def notify_appointment_confirmed(
        self,
        phone_number: str,
        service_name: str,
        date_time: str,
        stylist_name: str = None
    ) -> bool:
        """
        Notifica confirmación de cita.
        
        Args:
            phone_number: Número del cliente
            service_name: Nombre del servicio
            date_time: Fecha y hora formateada
            stylist_name: Nombre del estilista (opcional)
        
        Returns:
            True si se envió exitosamente
        """
        stylist_text = f" con {stylist_name}" if stylist_name else ""
        message = (
            f"✅ ¡Cita confirmada!\n\n"
            f"Servicio: {service_name}{stylist_text}\n"
            f"Fecha y hora: {date_time}\n\n"
            f"Te recordaremos 1 hora antes de tu cita. ¡Nos vemos!"
        )
        
        return await self.send_to_client(phone_number, message)
    
    async def notify_appointment_cancelled(
        self,
        phone_number: str,
        date_time: str
    ) -> bool:
        """
        Notifica cancelación de cita.
        
        Args:
            phone_number: Número del cliente
            date_time: Fecha y hora de la cita cancelada
        
        Returns:
            True si se envió exitosamente
        """
        message = (
            f"Tu cita del {date_time} ha sido cancelada.\n\n"
            f"Si deseas reagendar, simplemente escríbenos y buscaremos un nuevo horario."
        )
        
        return await self.send_to_client(phone_number, message)
    
    async def notify_salon(
        self,
        salon_phone: str,
        message: str
    ) -> bool:
        """
        Notifica al salón sobre cambios importantes.
        
        Args:
            salon_phone: Número de WhatsApp del salón
            message: Mensaje a enviar
        
        Returns:
            True si se envió exitosamente
        """
        return await self.send_to_client(salon_phone, message)

    # --- NOTIFICACIONES PARA ESTILISTAS ---

    async def notify_stylist_new_appointment(
        self,
        phone_number: str,
        client_name: str,
        service_name: str,
        date_time: str
    ) -> bool:
        """Notifica al estilista sobre una nueva cita agendada."""
        if not phone_number: return False
        message = (
            f"🆕 *Nueva cita agendada*\n\n"
            f"👤 Cliente: {client_name}\n"
            f"✂️ Servicio: {service_name}\n"
            f"📅 Fecha: {date_time}\n\n"
            f"¡Prepárate! ✨"
        )
        return await self.send_to_client(phone_number, message)

    async def notify_stylist_appointment_cancelled(
        self,
        phone_number: str,
        client_name: str,
        date_time: str
    ) -> bool:
        """Notifica al estilista sobre una cancelación."""
        if not phone_number: return False
        message = (
            f"❌ *Cita cancelada*\n\n"
            f"👤 Cliente: {client_name}\n"
            f"📅 Fecha: {date_time}\n\n"
            f"Este horario ahora está disponible."
        )
        return await self.send_to_client(phone_number, message)

    async def notify_stylist_appointment_rescheduled(
        self,
        phone_number: str,
        client_name: str,
        old_date_time: str,
        new_date_time: str
    ) -> bool:
        """Notifica al estilista sobre una reprogramación."""
        if not phone_number: return False
        message = (
            f"🔄 *Cita reprogramada*\n\n"
            f"👤 Cliente: {client_name}\n"
            f"📅 De: {old_date_time}\n"
            f"📅 A: {new_date_time}\n\n"
            f"Favor de actualizar tu agenda."
        )
        return await self.send_to_client(phone_number, message)

    async def notify_stylist_upcoming_appointment(
        self,
        phone_number: str,
        client_name: str,
        service_name: str,
        date_time: str
    ) -> bool:
        """Recordatorio de 30 minutos para el estilista."""
        if not phone_number: return False
        message = (
            f"⏰ *Próximo cliente en 30 min*\n\n"
            f"👤 Cliente: {client_name}\n"
            f"✂️ Servicio: {service_name}\n"
            f"🕒 Hora: {date_time}\n\n"
            f"¡Casi es hora!"
        )
        return await self.send_to_client(phone_number, message)
