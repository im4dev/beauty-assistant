import hmac
import hashlib
from core.config import settings


def verify_signature(body: bytes, signature_header: str) -> bool:
    """
    Meta firma cada request con HMAC-SHA256 usando tu APP_SECRET.
    El header llega como: "sha256=<hash>"

    Si no tienes APP_SECRET configurado, en desarrollo puedes
    retornar True, pero NUNCA en producción.
    """
    if not settings.APP_SECRET:
        # Solo permitido en desarrollo local
        return settings.ENV == "development"

    if not signature_header.startswith("sha256="):
        return False

    expected_signature = signature_header[len("sha256="):]

    computed = hmac.new(
        settings.APP_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed, expected_signature)