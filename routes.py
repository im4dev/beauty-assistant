from fastapi import APIRouter, HTTPException, Query, Depends, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, text
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime, timedelta
from typing import List
import asyncio
import hashlib
import hmac
import json
import time
from db.connection import AsyncSessionLocal
from db.models import Appointment, Salon, Client, Stylist, AppointmentStatus, Waitlist
from core.config import settings
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Dashboard"])



# Dependency para obtener la sesión de DB
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


# ─── Autenticación con usuario/contraseña ─────────────────────────────────────

def _token_key() -> bytes:
    return (settings.SECRET_KEY or f"dashboard:{settings.DASHBOARD_PASSWORD}").encode()


def create_token(username: str) -> str:
    """Token firmado: <usuario>.<expira_unix>.<hmac>"""
    expires = int(time.time()) + settings.TOKEN_TTL_HOURS * 3600
    payload = f"{username}.{expires}"
    sig = hmac.new(_token_key(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def require_auth(
    authorization: str = Header(None),
    token: str = Query(None),  # EventSource (SSE) no permite enviar headers
):
    raw = token
    if authorization and authorization.startswith("Bearer "):
        raw = authorization[len("Bearer "):]
    try:
        username, expires, sig = raw.rsplit(".", 2)
        expected = hmac.new(_token_key(), f"{username}.{expires}".encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig, expected) and int(expires) > time.time():
            return username
    except (AttributeError, ValueError):
        pass
    raise HTTPException(status_code=401, detail="No autenticado")


class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/auth/login")
async def login(credentials: LoginRequest):
    """
    Login simple con usuario y contraseña hardcodeados en .env
    
    Credenciales en DASHBOARD_USERNAME y DASHBOARD_PASSWORD
    """
    username = credentials.username
    password = credentials.password

    # Validar credenciales contra .env
    if username != settings.DASHBOARD_USERNAME or password != settings.DASHBOARD_PASSWORD:
        raise HTTPException(status_code=401, detail="Usuario o contraseña inválidos")
    
    return {
        "username": username,
        "token": create_token(username),
        "message": "Autenticado correctamente",
    }


# ─── Obtener todos los salones (desde PostgreSQL directo) ────────────────────

@router.get("/salons", dependencies=[Depends(require_auth)])
async def get_salons():
    """
    Obtiene todos los salones desde PostgreSQL de Supabase.
    Usa conexión directa en lugar de cliente anon para evitar restricciones RLS.
    """
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Salon).where(Salon.is_active == True)
            )
            salons = result.scalars().all()
            
            print(f"DEBUG: Salones desde PostgreSQL: {len(salons)}")
            
            if not salons:
                return {"salons": []}
            
            return {
                "salons": [
                    {"id": str(salon.id), "name": salon.name}
                    for salon in salons
                ]
            }
    except Exception as e:
        logger.error(f"Error al obtener salones: {str(e)}")
        print(f"DEBUG ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

# ─── SSE: Stream de citas en tiempo real ──────────────────────────────────────

@router.get("/salons/{salon_id}/appointments/stream", dependencies=[Depends(require_auth)])
async def stream_appointments(salon_id: str, date: str = None):
    """
    SSE endpoint que envía actualizaciones de citas en tiempo real para una fecha específica.
    """
    async def event_generator():
        while True:
            try:
                async with AsyncSessionLocal() as session:
                    from sqlalchemy.orm import joinedload
                    import zoneinfo
                    
                    # 1. Obtener zona horaria del salón para calcular "hoy" correctamente
                    salon_res = await session.execute(select(Salon).where(Salon.id == salon_id))
                    salon = salon_res.scalar_one_or_none()
                    tz_str = salon.timezone if salon and salon.timezone else "UTC"
                    tz = zoneinfo.ZoneInfo(tz_str)

                    # 2. Determinar el rango de búsqueda (24h de la fecha elegida)
                    if date:
                        try:
                            # Se espera formato YYYY-MM-DD
                            dt_obj = datetime.strptime(date, "%Y-%m-%d")
                            start_of_day = dt_obj.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=tz)
                        except:
                            start_of_day = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
                    else:
                        start_of_day = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
                    
                    end_of_day = start_of_day + timedelta(days=1)
                    
                    query = select(Appointment).options(
                        joinedload(Appointment.client),
                        joinedload(Appointment.stylist),
                        joinedload(Appointment.service)
                    ).where(
                        and_(
                            Appointment.salon_id == salon_id,
                            Appointment.start_time >= start_of_day,
                            Appointment.start_time < end_of_day,
                        )
                    ).order_by(Appointment.start_time)
                    
                    result = await session.execute(query)
                    appointments = result.unique().scalars().all()

                    appointments_data = []
                    for apt in appointments:
                        appointments_data.append({
                            "id": str(apt.id),
                            "client_name": apt.client.name or apt.client.wa_id if apt.client else "Sin cliente",
                            "stylist_name": apt.stylist.name if apt.stylist else "Sin estilista",
                            "service_name": apt.service_name or (apt.service.name if apt.service else "Sin servicio"),
                            "start_time": apt.start_time.isoformat(),
                            "end_time": apt.end_time.isoformat(),
                            "status": apt.status.value if isinstance(apt.status, AppointmentStatus) else apt.status,
                            "duration_minutes": (apt.end_time - apt.start_time).total_seconds() / 60,
                        })
                    
                    yield f"data: {json.dumps({'appointments': appointments_data})}\n\n"
                
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error(f"Error en SSE: {str(e)}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                await asyncio.sleep(10)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )

@router.get("/salons/{salon_id}/appointments", dependencies=[Depends(require_auth)])
async def get_appointments(
    salon_id: str,
    date: str = Query(None),  # formato: YYYY-MM-DD
    status: str = Query(None),  # confirmed, cancelled, no_show, completed
):
    """
    Trae citas del salón para un día específico o rango.
    Si no pasas date, trae hoy.
    """
    from sqlalchemy.orm import joinedload
    
    async with AsyncSessionLocal() as session:
        # Verificar que el salon existe
        result = await session.execute(select(Salon).where(Salon.id == salon_id))
        salon = result.scalar_one_or_none()
        if not salon:
            raise HTTPException(status_code=404, detail="Salón no encontrado")

        # Construir filtro de fecha
        if date:
            try:
                target_date = datetime.strptime(date, "%Y-%m-%d")
                start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
                end_of_day = start_of_day + timedelta(days=1)
            except ValueError:
                raise HTTPException(status_code=400, detail="Formato de fecha inválido: YYYY-MM-DD")
        else:
            start_of_day = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = start_of_day + timedelta(days=1)

        # Query con joinedload para cargar relaciones
        query = select(Appointment).options(
            joinedload(Appointment.client),
            joinedload(Appointment.stylist),
            joinedload(Appointment.service)
        ).where(
            and_(
                Appointment.salon_id == salon_id,
                Appointment.start_time >= start_of_day,
                Appointment.start_time < end_of_day,
            )
        )

        # Filtro por status si se proporciona
        if status:
            # Convertir a mayúsculas para comparar con el enum
            status_upper = status.upper()
            try:
                status_enum = AppointmentStatus[status_upper]
                query = query.where(Appointment.status == status_enum)
            except KeyError:
                raise HTTPException(status_code=400, detail=f"Status inválido: {status}. Valores válidos: scheduled, cancelled, completed, rescheduled")

        query = query.order_by(Appointment.start_time)
        result = await session.execute(query)
        appointments = result.unique().scalars().all()

        # Serializar respuesta
        appointments_data = []
        for apt in appointments:
            appointments_data.append({
                "id": str(apt.id),
                "client_name": apt.client.name or apt.client.wa_id if apt.client else "Sin cliente",
                "stylist_name": apt.stylist.name if apt.stylist else "Sin estilista",
                "service_name": apt.service_name or (apt.service.name if apt.service else "Sin servicio"),
                "start_time": apt.start_time.isoformat(),
                "end_time": apt.end_time.isoformat(),
                "status": apt.status.value if isinstance(apt.status, AppointmentStatus) else apt.status,
                "duration_minutes": (apt.end_time - apt.start_time).total_seconds() / 60,
            })

        return {
            "date": date or start_of_day.strftime("%Y-%m-%d"),
            "total": len(appointments_data),
            "appointments": appointments_data,
        }


# ─── Estadísticas del salón ───────────────────────────────────────────────────

@router.get("/salons/{salon_id}/stats", dependencies=[Depends(require_auth)])
async def get_stats(
    salon_id: str,
    days: int = Query(7),  # últimos N días
):
    """
    Estadísticas rápidas:
    - Total de citas confirmadas
    - Total de cancelaciones
    - Total de no-shows
    - Personas en lista de espera
    """
    async with AsyncSessionLocal() as session:
        # Verificar que el salon existe
        result = await session.execute(select(Salon).where(Salon.id == salon_id))
        salon = result.scalar_one_or_none()
        if not salon:
            raise HTTPException(status_code=404, detail="Salón no encontrado")

        since = datetime.utcnow() - timedelta(days=days)

        # Contar por status usando ENUM
        confirmed = await session.scalar(
            select(func.count(Appointment.id)).where(
                and_(
                    Appointment.salon_id == salon_id,
                    Appointment.status == AppointmentStatus.SCHEDULED,
                    Appointment.start_time >= since,
                )
            )
        )

        cancelled = await session.scalar(
            select(func.count(Appointment.id)).where(
                and_(
                    Appointment.salon_id == salon_id,
                    Appointment.status == AppointmentStatus.CANCELLED,
                    Appointment.start_time >= since,
                )
            )
        )

        no_show = await session.scalar(
            select(func.count(Appointment.id)).where(
                and_(
                    Appointment.salon_id == salon_id,
                    Appointment.status == AppointmentStatus.RESCHEDULED,
                    Appointment.start_time >= since,
                )
            )
        )

        completed = await session.scalar(
            select(func.count(Appointment.id)).where(
                and_(
                    Appointment.salon_id == salon_id,
                    Appointment.status == AppointmentStatus.COMPLETED,
                    Appointment.start_time >= since,
                )
            )
        )

        # Lista de espera
        waitlist_count = await session.scalar(
            select(func.count()).select_from(
                Appointment
            ).where(
                Appointment.salon_id == salon_id
            )
        )

        return {
            "period_days": days,
            "confirmed": confirmed or 0,
            "cancelled": cancelled or 0,
            "no_show": no_show or 0,
            "completed": completed or 0,
            "total": (confirmed or 0) + (cancelled or 0) + (no_show or 0) + (completed or 0),
        }


# ─── Próximas citas (siguientes 7 días) ──────────────────────────────────────

@router.get("/salons/{salon_id}/upcoming", dependencies=[Depends(require_auth)])
async def get_upcoming(salon_id: str):
    """Próximas 10 citas confirmadas"""
    from sqlalchemy.orm import joinedload
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Salon).where(Salon.id == salon_id))
        salon = result.scalar_one_or_none()
        if not salon:
            raise HTTPException(status_code=404, detail="Salón no encontrado")

        query = select(Appointment).options(
            joinedload(Appointment.client),
            joinedload(Appointment.stylist)
        ).where(
            and_(
                Appointment.salon_id == salon_id,
                Appointment.status == AppointmentStatus.SCHEDULED,
                Appointment.start_time >= datetime.utcnow(),
            )
        ).order_by(Appointment.start_time).limit(10)

        result = await session.execute(query)
        appointments = result.unique().scalars().all()

        appointments_data = []
        for apt in appointments:
            appointments_data.append({
                "id": str(apt.id),
                "client_name": apt.client.name or apt.client.wa_id if apt.client else "Sin cliente",
                "stylist_name": apt.stylist.name if apt.stylist else "Sin estilista",
                "start_time": apt.start_time.isoformat(),
                "status": apt.status.value if isinstance(apt.status, AppointmentStatus) else apt.status,
            })

        return {"appointments": appointments_data}


# ─── Webhook para respuestas de lista de espera ───────────────────────────────

@router.post("/waitlist/respond", dependencies=[Depends(require_auth)])
async def waitlist_response(
    waitlist_id: str,
    accepted: bool,
    salon_id: str,
    freed_start_time: str,
    service_name: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Procesa la respuesta de un cliente a una oferta de lista de espera.
    
    Este endpoint es llamado cuando un cliente responde "sí" o "no" a una oferta
    de horario disponible desde la cascada inversa.
    """
    from appointments.waitlist import WaitlistManager
    from datetime import datetime
    
    try:
        # Parsear la fecha/hora liberada
        freed_dt = datetime.fromisoformat(freed_start_time)
        
        # Procesar la respuesta
        waitlist_manager = WaitlistManager(db)
        success, msg = await waitlist_manager.handle_waitlist_response(
            waitlist_id=waitlist_id,
            accepted=accepted,
            salon_id=salon_id,
            freed_start_time=freed_dt,
            service_name=service_name
        )
        
        if success:
            return {"status": "success", "message": msg}
        else:
            return {"status": "error", "message": msg}
            
    except Exception as e:
        logger.error(f"Error procesando respuesta de lista de espera: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")