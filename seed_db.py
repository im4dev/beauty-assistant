import asyncio
from db.connection import AsyncSessionLocal, engine
from db.models import Salon, Base

async def seed_data():
    print("⏳ Conectando a la base de datos...")
    
    # Aseguramos que las tablas existan (por si acaso)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        # 1. Creamos el salón de prueba
        test_salon = Salon(
            name="Beauty Lab de Prueba",
            wa_phone_number_id="1002421366288721",
            timezone="America/Guayaquil",
            is_active=True
        )

        try:
            session.add(test_salon)
            await session.commit()
            print("---")
            print(f"✅ Salón '{test_salon.name}' creado con éxito.")
            print(f"🔑 Tu ID de Salón es: {test_salon.id}")
            print(f"📱 WA Phone ID registrado: {test_salon.wa_phone_number_id}")
            print("---")
            print("Copia el 'ID de Salón' (UUID), lo necesitaremos pronto.")
            
        except Exception as e:
            await session.rollback()
            print(f"❌ Error al crear el salón: {e}")
            print("Es posible que el wa_phone_number_id ya exista.")

if __name__ == "__main__":
    asyncio.run(seed_data())