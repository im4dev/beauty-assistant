from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from routes import router as api_router
from webhooks.whatsapp import router as whatsapp_router
from db.connection import init_db, AsyncSessionLocal
from fastapi.responses import FileResponse
from notifications.scheduler import ReminderScheduler
import logging
import asyncio

# Configuración básica de logging para ver logs en consola
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:     %(message)s"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializar DB al arrancar
    await init_db()
    
    # Iniciar scheduler de recordatorios como tarea de fondo
    scheduler = ReminderScheduler(AsyncSessionLocal)
    scheduler_task = asyncio.create_task(scheduler.start_background_task(interval_minutes=5))
    
    yield
    
    # Limpiar: cancelar tarea de scheduler al apagar
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Beauty Assistant",
    description="Asistente de agendamiento para talleres de belleza",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS para el dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción: especificar dominio
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
 
app.include_router(whatsapp_router, prefix="/webhook", tags=["WhatsApp"])
app.include_router(api_router)

app.mount("/static", StaticFiles(directory="./static"), name="static")


@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/")
async def root():
    return FileResponse('static/index.html')