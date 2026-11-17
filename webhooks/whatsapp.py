from fastapi import APIRouter, Request, HTTPException, Query, BackgroundTasks
from core.orchestrator import Orchestrator
from webhooks.verify import verify_signature
from tenants.resolver import resolve_tenant
from services.whatsapp_client import WhatsAppClient
from db.connection import AsyncSessionLocal
import time
import logging


logger = logging.getLogger(__name__)
router = APIRouter()
wa_client = WhatsAppClient()

# ─── Verificación del webhook (Meta lo llama una vez al configurar) ───────────

@router.get("")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
):
    """
    Meta llama a este endpoint GET para verificar que el webhook es tuyo.
    Debes tener VERIFY_TOKEN en tu .env con el mismo valor que pusiste en
    el panel de Meta Developers.
    """
    from core.config import settings

    if hub_mode == "subscribe" and hub_verify_token == settings.VERIFY_TOKEN:
        logger.info("Webhook verificado correctamente")
        return int(hub_challenge)

    raise HTTPException(status_code=403, detail="Token de verificación inválido")


# ─── Recepción de mensajes entrantes ─────────────────────────────────────────

# IDs de mensajes ya procesados. Meta reintenta la entrega si no recibe 200
# rápido, así que filtramos duplicados (en memoria: basta con un solo proceso).
_seen_message_ids: dict[str, float] = {}
_SEEN_TTL_SECONDS = 600


def _already_seen(message_id: str) -> bool:
    now = time.time()
    for mid, ts in list(_seen_message_ids.items()):
        if now - ts > _SEEN_TTL_SECONDS:
            del _seen_message_ids[mid]
    if message_id in _seen_message_ids:
        return True
    _seen_message_ids[message_id] = now
    return False


@router.post("")
async def receive_message(request: Request, background_tasks: BackgroundTasks):
    """
    Meta envía aquí todos los mensajes entrantes.
    Estructura típica del body:
    {
      "object": "whatsapp_business_account",
      "entry": [{
        "changes": [{
          "value": {
            "metadata": { "phone_number_id": "..." },
            "messages": [{ "from": "593...", "text": { "body": "Hola" } }]
          }
        }]
      }]
    }

    Respondemos 200 de inmediato y procesamos en segundo plano: si tardamos
    (el LLM puede tardar varios segundos), Meta reenvía el mismo mensaje.
    """
    # 1. Validar firma de Meta (seguridad)
    body_bytes = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not verify_signature(body_bytes, signature):
        raise HTTPException(status_code=401, detail="Firma inválida")

    payload = await request.json()

    # 2. Ignorar si no es un mensaje de WhatsApp
    if payload.get("object") != "whatsapp_business_account":
        return {"status": "ignored"}

    # 3. Extraer mensajes del payload
    current_time = int(time.time())
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            messages = value.get("messages", [])
            phone_number_id = value.get("metadata", {}).get("phone_number_id")

            for message in messages:
                # Solo procesar mensajes de texto por ahora
                if message.get("type") != "text":
                    logger.info(f"Tipo de mensaje ignorado: {message.get('type')}")
                    continue

                # REGLA DE ORO: Si el mensaje tiene más de 120 segundos, no lo proceses
                if current_time - int(message.get("timestamp", 0)) > 120:
                    logger.info("⏳ Ignorando mensaje antiguo para evitar spam.")
                    continue

                if _already_seen(message["id"]):
                    logger.info(f"Mensaje duplicado ignorado: {message['id']}")
                    continue

                background_tasks.add_task(
                    process_message,
                    phone_number_id,
                    message["from"],
                    message["text"]["body"],
                )

    return {"status": "ok"}


async def process_message(phone_number_id: str, sender_phone: str, text: str):
    logger.info(f"Mensaje recibido de {sender_phone}: {text[:50]}")
    try:
        async with AsyncSessionLocal() as db_session:
            # 4. Resolver a qué salón pertenece este número destino
            tenant = await resolve_tenant(phone_number_id, db_session)
            if not tenant:
                return

            # 5. Pasar al orquestador para procesar
            orchestrator = Orchestrator(db_session)
            response_text = await orchestrator.handle_message(
                phone_number=sender_phone,
                message_text=text,
                salon_id=tenant.id,
            )

            # 6. Enviar la respuesta por WhatsApp 🚀
            if response_text:
                await wa_client.send_text_message(sender_phone, response_text)
    except Exception:
        logger.exception(f"❌ Error procesando mensaje de {sender_phone}")
