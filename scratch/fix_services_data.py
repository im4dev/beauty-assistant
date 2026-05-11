import asyncio
import sys
import os
import unicodedata
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.connection import AsyncSessionLocal
from db.models import Service, Appointment

def normalize_string(s):
    if not s:
        return ""
    # Remove accents and lowercase
    n = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    return n.lower().strip()

CATEGORY_MAP = {
    "colorimetria": "Colorimetría",
    "barberia": "Barbería",
    "peluqueria": "Peluquería",
    "estetica": "Estética",
    "manicura": "Manicura",
    "pedicura": "Pedicura",
    "maquillaje": "Maquillaje",
}

def get_canonical_category(cat):
    norm = normalize_string(cat)
    return CATEGORY_MAP.get(norm, cat.title() if cat else "Otros")

async def fix_services():
    async with AsyncSessionLocal() as session:
        print("Fetching all services...")
        res = await session.execute(select(Service))
        services = res.scalars().all()
        
        # 1. Normalize categories
        for s in services:
            canonical = get_canonical_category(s.category)
            if s.category != canonical:
                print(f"Updating category for '{s.name}': '{s.category}' -> '{canonical}'")
                s.category = canonical
        
        await session.commit()
        
        # 2. Find duplicates
        # We'll group by (salon_id, name, category)
        print("Checking for duplicates...")
        res = await session.execute(select(Service))
        services = res.scalars().all()
        
        seen = {} # (salon_id, name, category) -> primary_service_id
        duplicates = []
        
        for s in services:
            key = (s.salon_id, normalize_string(s.name), normalize_string(s.category))
            if key in seen:
                primary_id = seen[key]
                duplicates.append((s, primary_id))
            else:
                seen[key] = s.id
        
        if not duplicates:
            print("No duplicates found.")
            return

        print(f"Found {len(duplicates)} duplicates. Merging...")
        
        for dup_service, primary_id in duplicates:
            print(f"Merging duplicate service '{dup_service.name}' ({dup_service.id}) into {primary_id}")
            
            # Reassign appointments
            await session.execute(
                update(Appointment)
                .where(Appointment.service_id == dup_service.id)
                .values(service_id=primary_id)
            )
            
            # Delete duplicate service
            await session.execute(delete(Service).where(Service.id == dup_service.id))
        
        await session.commit()
        print("Cleanup complete!")

if __name__ == "__main__":
    asyncio.run(fix_services())
