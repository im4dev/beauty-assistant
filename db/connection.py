from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from core.config import settings

# 1. Creamos el motor asíncrono
# echo=False silencia las consultas SQL en la consola (útil en desarrollo poner en True)
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    pool_size=10,
    max_overflow=20
)

# 2. Creamos la fábrica de sesiones
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# 3. Función para obtener la sesión de DB (Dependency Injection para FastAPI)
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# 4. Función para inicializar las tablas (Paso de fuego inicial)
async def init_db():
    from db.models import Base # Importación local para evitar importes circulares
    async with engine.begin() as conn:
        # En producción podrías preferir usar Alembic
        # Pero para empezar, esto creará las tablas si no existen
        await conn.run_sync(Base.metadata.create_all)