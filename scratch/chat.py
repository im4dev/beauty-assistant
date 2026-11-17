"""
Chat de terminal que simula ser un cliente escribiendo por WhatsApp.
Usa el mismo orquestador que el webhook, pero los mensajes salientes
(respuestas, avisos a estilistas, ofertas de lista de espera) se imprimen
en vez de enviarse a Meta.

Uso: python -m scratch.chat [numero_cliente]   (por defecto 593990000099)
"""
import asyncio
import logging
import sys

from sqlalchemy import select

from core.config import settings
from core.orchestrator import Orchestrator
from db.connection import AsyncSessionLocal
from db.models import Salon
from services.whatsapp_client import WhatsAppClient


async def fake_send(self, to_phone: str, message: str):
    print(f"\n\033[90m[WhatsApp → {to_phone}]\033[0m\n{message}\n")
    return {"fake": True}


WhatsAppClient.send_text_message = fake_send


async def main():
    phone = sys.argv[1] if len(sys.argv) > 1 else "593990000099"

    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Salon).where(Salon.wa_phone_number_id == settings.WHATSAPP_PHONE_ID))
        salon = res.scalar_one_or_none()
    if not salon:
        sys.exit("No hay salón para WHATSAPP_PHONE_ID; ejecuta antes: python -m scratch.seed_demo")

    print(f"💬 Chateando con '{salon.name}' como {phone}. Ctrl+C para salir.\n")
    while True:
        try:
            text = await asyncio.to_thread(input, "\033[1mtú>\033[0m ")
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not text.strip():
            continue
        async with AsyncSessionLocal() as db:
            reply = await Orchestrator(db).handle_message(
                phone_number=phone, message_text=text, salon_id=salon.id
            )
        print(f"\n\033[95mbot>\033[0m {reply}\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
