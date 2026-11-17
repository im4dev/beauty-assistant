"""
Crea un salón de demo con estilistas, servicios, clientes y citas para hoy y mañana.
Es idempotente: si ya existe un salón con ese wa_phone_number_id no hace nada.

Uso: python -m scratch.seed_demo   (usa DATABASE_URL y WHATSAPP_PHONE_ID del entorno/.env)
"""
import asyncio
import zoneinfo
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from core.config import settings
from db.connection import AsyncSessionLocal, init_db
from db.models import Appointment, AppointmentStatus, Client, Salon, Service, Stylist

TIMEZONE = "America/Guayaquil"

SERVICES = [
    # (nombre, categoría, precio, minutos)
    ("Corte de cabello mujer", "Peluquería", "15.00", 45),
    ("Corte de cabello hombre", "Barbería", "8.00", 30),
    ("Arreglo de barba", "Barbería", "6.00", 30),
    ("Tinte completo", "Colorimetría", "45.00", 120),
    ("Mechas / Balayage", "Colorimetría", "70.00", 150),
    ("Manicura clásica", "Manicura", "10.00", 45),
    ("Pedicura spa", "Pedicura", "18.00", 60),
    ("Limpieza facial", "Estética", "25.00", 60),
]

STYLISTS = [
    ("Valeria Torres", "Colorista"),
    ("Andrés Mejía", "Corte y barbería"),
    ("Camila Ruiz", "Manicura y estética"),
]

CLIENTS = [
    ("María López", "593990000001"),
    ("José Andrade", "593990000002"),
    ("Lucía Paredes", "593990000003"),
    ("Daniela Vega", "593990000004"),
]

# (día relativo, hora, minuto, índice servicio, índice estilista, índice cliente, estado)
APPOINTMENTS = [
    (0, 9, 0, 0, 0, 0, AppointmentStatus.SCHEDULED),
    (0, 10, 0, 1, 1, 1, AppointmentStatus.SCHEDULED),
    (0, 14, 0, 5, 2, 2, AppointmentStatus.SCHEDULED),
    (0, 15, 0, 7, 2, 3, AppointmentStatus.CANCELLED),
    (1, 9, 30, 3, 0, 3, AppointmentStatus.SCHEDULED),
    (1, 11, 0, 2, 1, 1, AppointmentStatus.SCHEDULED),
    (-1, 10, 0, 6, 2, 0, AppointmentStatus.COMPLETED),
    (-1, 14, 0, 0, 0, 2, AppointmentStatus.COMPLETED),
]


async def seed():
    await init_db()
    phone_id = settings.WHATSAPP_PHONE_ID
    tz = zoneinfo.ZoneInfo(TIMEZONE)

    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(Salon).where(Salon.wa_phone_number_id == phone_id))
        if existing.scalar_one_or_none():
            print(f"Ya existe un salón con wa_phone_number_id={phone_id}, no se hace nada.")
            return

        salon = Salon(name="Studio Aurora", wa_phone_number_id=phone_id, timezone=TIMEZONE)
        db.add(salon)
        await db.flush()

        services = [
            Service(salon_id=salon.id, name=n, category=c, price=Decimal(p), duration_minutes=m)
            for n, c, p, m in SERVICES
        ]
        stylists = [Stylist(salon_id=salon.id, name=n, specialty=s) for n, s in STYLISTS]
        clients = [Client(salon_id=salon.id, name=n, wa_id=w) for n, w in CLIENTS]
        db.add_all(services + stylists + clients)
        await db.flush()

        today = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        for day, hour, minute, svc, sty, cli, status in APPOINTMENTS:
            start = today + timedelta(days=day, hours=hour, minutes=minute)
            service = services[svc]
            db.add(Appointment(
                salon_id=salon.id,
                client_id=clients[cli].id,
                stylist_id=stylists[sty].id,
                service_id=service.id,
                service_name=service.name,
                start_time=start,
                end_time=start + timedelta(minutes=service.duration_minutes),
                status=status,
            ))

        await db.commit()
        print(f"✅ Salón '{salon.name}' creado ({salon.id}) con {len(services)} servicios, "
              f"{len(stylists)} estilistas y {len(APPOINTMENTS)} citas.")


if __name__ == "__main__":
    asyncio.run(seed())
