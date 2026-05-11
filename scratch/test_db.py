import asyncio
import os
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

DATABASE_URL = "postgresql+asyncpg://postgres:VWhVj4FflWYZcmv2@db.etjbilmwkrlvkjlngero.supabase.co:5432/postgres"

async def test_conn():
    print(f"Connecting to {DATABASE_URL}...")
    engine = create_async_engine(DATABASE_URL)
    async with engine.connect() as conn:
        print("Connected!")
        res = await conn.execute(text("SELECT count(*) FROM services"))
        count = res.scalar()
        print(f"Total services: {count}")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(test_conn())
