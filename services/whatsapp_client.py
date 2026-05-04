from core.config import settings
import httpx

class WhatsAppClient:
    def __init__(self):
        self.token = settings.WA_ACCESS_TOKEN
        self.phone_number_id = settings.WHATSAPP_PHONE_ID
        self.base_url = f"https://graph.facebook.com/v19.0/{self.phone_number_id}/messages"

    async def send_text_message(self, to_phone: str, message: str):
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "text",
            "text": {"preview_url": False, "body": message},
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.base_url, json=payload, headers=headers)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                print(f"❌ Error enviando a WhatsApp: {str(e)}")
                return None