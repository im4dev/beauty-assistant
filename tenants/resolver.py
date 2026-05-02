from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import Salon

async def resolve_tenant(phone_number_id: str, db: AsyncSession):
    """
    Busca el salón en la base de datos usando el phone_number_id de Meta.
    """
    # 1. Creamos la consulta
    query = select(Salon).where(Salon.wa_phone_number_id == phone_number_id)
    
    # 2. Ejecutamos
    result = await db.execute(query)
    
    # 3. Obtenemos el salón
    salon = result.scalar_one_or_none()
    
    if not salon:
        print(f"⚠️ Alerta: Se recibió un mensaje para el ID {phone_number_id} pero no existe en la DB.")
        return None
        
    return salon