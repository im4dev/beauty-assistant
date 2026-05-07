import asyncio
from sqlalchemy import select
from db.connection import AsyncSessionLocal
from db.models import Appointment

async def main():
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Appointment))
        appts = res.scalars().all()
        for a in appts:
            print(f"ID: {a.id}, Status: {a.status}, Start: {a.start_time}, End: {a.end_time}, Client: {a.client_id}")

asyncio.run(main())
