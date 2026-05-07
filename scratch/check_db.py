import asyncio
import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from db.models import Appointment, Salon
from core.config import settings

async def check_db():
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Check all appointments
        result = await session.execute(select(Appointment))
        appointments = result.scalars().all()
        print(f"Total appointments in DB: {len(appointments)}")
        for apt in appointments:
            print(f"ID: {apt.id}, Salon: {apt.salon_id}, Start: {apt.start_time}, Status: {apt.status}")
        
        # Check current UTC time
        from datetime import datetime
        print(f"Current UTC time: {datetime.utcnow()}")

if __name__ == "__main__":
    asyncio.run(check_db())
