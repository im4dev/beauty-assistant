"""
Tests manuales con DeepSeek API real.

Este script simula conversaciones reales con el cliente usando la API real de DeepSeek.
REQUIERE: DEEPSEEK_API_KEY en .env

Uso:
    python tests/manual_test.py

O con pytest:
    pytest tests/manual_test.py -v -s
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Agregar el directorio raíz al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from db.connection import AsyncSessionLocal
from core.orchestrator import Orchestrator
from core.llm import LLMService
from sqlalchemy import select
from db.models import Salon, Client, Service, Stylist


async def setup_test_data(db_session):
    """Crea datos de prueba para el test manual."""
    from db.models import Salon, Client, Service, Stylist
    import uuid
    
    # Crear salón
    salon = Salon(
        id=uuid.uuid4(),
        name="Salón Test Manual",
        wa_phone_number_id="test_phone_id",
        timezone="America/New_York",
        is_active=True
    )
    db_session.add(salon)
    
    # Crear estilista
    stylist = Stylist(
        id=uuid.uuid4(),
        salon_id=salon.id,
        name="María",
        specialty="Colorista",
        is_active=True
    )
    db_session.add(stylist)
    
    # Crear servicio
    service = Service(
        id=uuid.uuid4(),
        salon_id=salon.id,
        name="Corte de Cabello",
        category="Peluquería",
        price=15.00,
        duration_minutes=30,
        is_active=True
    )
    db_session.add(service)
    
    # Crear cliente
    client = Client(
        id=uuid.uuid4(),
        salon_id=salon.id,
        name="Juan Pérez",
        wa_id="5939876543210"
    )
    db_session.add(client)
    
    await db_session.commit()
    await db_session.refresh(salon)
    await db_session.refresh(stylist)
    await db_session.refresh(service)
    await db_session.refresh(client)
    
    return salon, stylist, service, client


async def test_conversation_booking():
    """
    Test manual: Flujo completo de agendar cita.
    
    Simula una conversación real con el cliente usando DeepSeek API.
    """
    print("\n" + "="*60)
    print("TEST MANUAL: Flujo completo de agendar cita")
    print("="*60)
    
    async with AsyncSessionLocal() as db:
        # Setup datos de prueba
        salon, stylist, service, client = await setup_test_data(db)
        
        orchestrator = Orchestrator(db)
        phone_number = client.wa_id
        
        messages = [
            "Hola, quiero una cita",
            "Para corte de cabello",
            "El más cercano que tengan",
            "Sí, confirmado"
        ]
        
        print(f"\n📱 Cliente: {client.name}")
        print(f"🏢 Salón: {salon.name}")
        print(f"💇 Estilista: {stylist.name}")
        print(f"✂️ Servicio: {service.name}")
        print("-"*60)
        
        for i, msg in enumerate(messages, 1):
            print(f"\n--- Mensaje {i} ---")
            print(f"Cliente: {msg}")
            
            try:
                response = await orchestrator.handle_message(
                    phone_number=phone_number,
                    message_text=msg,
                    salon_id=str(salon.id)
                )
                
                print(f"Bot: {response}")
                
                # Validaciones básicas
                assert response is not None, "La respuesta no debe ser None"
                assert len(response) > 0, "La respuesta no debe estar vacía"
                assert "error" not in response.lower(), f"Error en respuesta: {response}"
                
                print("✅ Respuesta válida")
                
            except Exception as e:
                print(f"❌ Error: {e}")
                raise
        
        print("\n" + "="*60)
        print("✅ TEST COMPLETADO EXITOSAMENTE")
        print("="*60)


async def test_conversation_cancellation():
    """
    Test manual: Flujo de cancelar cita.
    """
    print("\n" + "="*60)
    print("TEST MANUAL: Flujo de cancelar cita")
    print("="*60)
    
    async with AsyncSessionLocal() as db:
        # Setup datos
        salon, stylist, service, client = await setup_test_data(db)
        
        # Crear una cita existente
        from db.models import Appointment, AppointmentStatus
        import uuid
        
        appointment = Appointment(
            id=uuid.uuid4(),
            salon_id=salon.id,
            client_id=client.id,
            stylist_id=stylist.id,
            service_id=service.id,
            service_name=service.name,
            start_time=datetime.now() + timedelta(days=1, hours=14),
            end_time=datetime.now() + timedelta(days=1, hours=14, minutes=30),
            status=AppointmentStatus.SCHEDULED
        )
        db.add(appointment)
        await db.commit()
        
        orchestrator = Orchestrator(db)
        phone_number = client.wa_id
        
        messages = [
            "Necesito cancelar mi cita",
            "Sí, confirmo la cancelación"
        ]
        
        print(f"\n📱 Cliente: {client.name}")
        print(f"📅 Cita existente: {appointment.start_time}")
        print("-"*60)
        
        for i, msg in enumerate(messages, 1):
            print(f"\n--- Mensaje {i} ---")
            print(f"Cliente: {msg}")
            
            try:
                response = await orchestrator.handle_message(
                    phone_number=phone_number,
                    message_text=msg,
                    salon_id=str(salon.id)
                )
                
                print(f"Bot: {response}")
                assert response is not None and len(response) > 0
                print("✅ Respuesta válida")
                
            except Exception as e:
                print(f"❌ Error: {e}")
                raise
        
        # Verificar que la cita fue cancelada
        await db.refresh(appointment)
        assert appointment.status == AppointmentStatus.CANCELLED, "La cita debe estar cancelada"
        
        print("\n" + "="*60)
        print("✅ TEST COMPLETADO EXITOSAMENTE")
        print("="*60)


async def test_llm_directly():
    """
    Test directo al LLM para validar la API de DeepSeek.
    """
    print("\n" + "="*60)
    print("TEST MANUAL: LLM Directo (DeepSeek API)")
    print("="*60)
    
    llm = LLMService()
    
    test_messages = [
        "Hola, quiero una cita para mañana",
        "Cancelo mi cita",
        "¿Qué servicios ofrecen?",
        "Necesito cambiar mi hora"
    ]
    
    for msg in test_messages:
        print(f"\n--- Analizando: {msg} ---")
        
        try:
            result = await llm.analyze_message(
                message_text=msg,
                client_name="Juan",
                current_entities={},
                context_services="- Corte de Cabello: $15 (30 min)",
                history="",
                current_step="IDLE",
                salon_timezone="America/New_York"
            )
            
            print(f"Intent: {result.get('intent')}")
            print(f"Entities: {result.get('entities')}")
            print(f"Response: {result.get('response_message')}")
            print("✅ Análisis exitoso")
            
            assert "intent" in result, "Debe tener intent"
            assert "entities" in result, "Debe tener entities"
            assert "response_message" in result, "Debe tener response_message"
            
        except Exception as e:
            print(f"❌ Error: {e}")
            raise
    
    print("\n" + "="*60)
    print("✅ TEST COMPLETADO EXITOSAMENTE")
    print("="*60)


async def test_availability_service():
    """
    Test manual del servicio de disponibilidad.
    """
    print("\n" + "="*60)
    print("TEST MANUAL: Availability Service")
    print("="*60)
    
    async with AsyncSessionLocal() as db:
        # Setup datos
        salon, stylist, service, client = await setup_test_data(db)
        
        from services.availability import AvailabilityService
        
        # Test 1: Horario disponible
        print("\n--- Test 1: Horario disponible ---")
        available_time = datetime.now() + timedelta(days=1, hours=14)
        is_available, msg = await AvailabilityService.check_availability(
            db, str(salon.id), available_time, 30
        )
        print(f"Hora: {available_time}")
        print(f"Disponible: {is_available}")
        print(f"Mensaje: {msg}")
        print("✅ Test 1 completado")
        
        # Test 2: Horario ocupado
        print("\n--- Test 2: Horario ocupado ---")
        from db.models import Appointment, AppointmentStatus
        import uuid
        
        # Crear cita en ese horario
        appointment = Appointment(
            id=uuid.uuid4(),
            salon_id=salon.id,
            client_id=client.id,
            stylist_id=stylist.id,
            service_id=service.id,
            service_name=service.name,
            start_time=available_time,
            end_time=available_time + timedelta(minutes=30),
            status=AppointmentStatus.SCHEDULED
        )
        db.add(appointment)
        await db.commit()
        
        is_available, msg = await AvailabilityService.check_availability(
            db, str(salon.id), available_time, 30
        )
        print(f"Hora: {available_time}")
        print(f"Disponible: {is_available}")
        print(f"Mensaje: {msg}")
        assert is_available is False, "Debe estar ocupado"
        print("✅ Test 2 completado")
        
        # Test 3: Obtener slots disponibles
        print("\n--- Test 3: Slots disponibles ---")
        slots = await AvailabilityService.get_available_slots(
            db, str(salon.id), available_time.date(), 30
        )
        print(f"Fecha: {available_time.date()}")
        print(f"Slots disponibles: {slots}")
        print("✅ Test 3 completado")
    
    print("\n" + "="*60)
    print("✅ TEST COMPLETADO EXITOSAMENTE")
    print("="*60)


async def main():
    """Ejecuta todos los tests manuales."""
    print("\n" + "#"*60)
    print("# TESTS MANUALES - BEAUTY ASSISTANT")
    print("# Requiere DEEPSEEK_API_KEY en .env")
    print("#"*60)
    
    # Verificar API key
    from core.config import settings
    if not settings.DEEPSEEK_API_KEY:
        print("\n❌ ERROR: DEEPSEEK_API_KEY no encontrada en .env")
        print("Por favor agrega: DEEPSEEK_API_KEY=tu_clave_aqui")
        return
    
    try:
        # Test 1: LLM directo
        await test_llm_directly()
        
        # Test 2: Availability Service
        await test_availability_service()
        
        # Test 3: Conversación de agendar
        await test_conversation_booking()
        
        # Test 4: Conversación de cancelar
        await test_conversation_cancellation()
        
        print("\n" + "#"*60)
        print("# ✅ TODOS LOS TESTS MANUALES COMPLETADOS")
        print("#"*60 + "\n")
        
    except Exception as e:
        print(f"\n❌ ERROR GENERAL: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
