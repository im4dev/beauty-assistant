from fastapi import APIRouter, Request, HTTPException, Query
from core.orchestrator import Orchestrator
from webhooks.verify import verify_signature
from tenants.resolver import resolve_tenant
from db.connection import AsyncSessionLocal
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


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

@router.post("")
async def receive_message(request: Request):
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

                sender_phone = message["from"]
                text = message["text"]["body"]
                message_id = message["id"]

                logger.info(f"Mensaje recibido de {sender_phone}: {text[:50]}")

                # 5. Pasar al orquestador para procesar
                async with AsyncSessionLocal() as db_session:
                    # 4. Resolver a qué salón pertenece este número destino
                    tenant = await resolve_tenant(phone_number_id, db_session)

                    # Instanciamos el orquestador con la sesión de DB
                    orchestrator = Orchestrator(db_session)
                    
                    # Llamamos al método handle_message que definimos
                    response_text = await orchestrator.handle_message(
                        phone_number=sender_phone,
                        message_text=text,
                        salon_id=tenant.id  # El ID del salón que resolvió tu tenants/resolver.py
                    )
                    
                    # 6. (Próximamente) Aquí enviarías response_text de vuelta a WhatsApp
                    print(f"🤖 Respuesta generada: {response_text}")

    return {"status": "ok"}