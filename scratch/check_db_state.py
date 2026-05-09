import asyncio
import os
import sys
# Añadir el path actual al sys.path para importar db.models
sys.path.append(os.getcwd())

from sqlalchemy import select, func
from db.models import Stylist, Appointment, AppointmentStatus, Service
from db.connection import AsyncSessionLocal

async def check():
    async with AsyncSessionLocal() as db:
        # 1. Estilistas
        res = await db.execute(select(Stylist).where(Stylist.is_active == True))
        stylists = res.scalars().all()
        print(f"--- Estilistas Activos: {len(stylists)} ---")
        for s in stylists:
            print(f"ID: {s.id} | Nombre: {s.name}")

        # 2. Citas de hoy (2026-05-09)
        from datetime import datetime, time
        day_start = datetime(2026, 5, 9, 0, 0)
        day_end = datetime(2026, 5, 9, 23, 59)
        
        res = await db.execute(
            select(Appointment)
            .where(Appointment.start_time >= day_start, Appointment.start_time <= day_end)
            .order_by(Appointment.start_time)
        )
        appts = res.scalars().all()
        print(f"\n--- Citas para hoy (09/05) ---")
        for a in appts:
            print(f"Hora: {a.start_time} - {a.end_time} | Status: {a.status} | Servicio: {a.service_name}")

if __name__ == "__main__":
    asyncio.run(check())
