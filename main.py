from fastapi import FastAPI
from contextlib import asynccontextmanager

from webhooks.whatsapp import router as whatsapp_router
from db.connection import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializar DB al arrancar
    await init_db()
    yield


app = FastAPI(
    title="Beauty Assistant",
    description="Asistente de agendamiento para talleres de belleza",
    version="0.1.0",
    #lifespan=lifespan,
)

app.include_router(whatsapp_router, prefix="/webhook", tags=["WhatsApp"])


@app.get("/health")
async def health():
    return {"status": "ok"}