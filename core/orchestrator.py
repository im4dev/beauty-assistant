from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.session import SessionManager
from core.llm import LLMService

from db.models import Client

class Orchestrator:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self.session_manager = SessionManager(db_session)
        self.llm = LLMService()

    async def handle_message(self, phone_number: str, message_text: str, salon_id: str):
        # 1. Recuperar contexto de la sesión
        session = await self.session_manager.get_or_create(phone_number, salon_id)
        
        # 2. Buscar si el cliente ya existe en este salón
        result = await self.db.execute(
            select(Client).where(Client.wa_id == phone_number, Client.salon_id == salon_id)
        )
        client = result.scalar_one_or_none()

    # --- CAMBIO CRÍTICO: REVISAR EL ESTADO PRIMERO ---
        if session.current_step == "AWAITING_NAME":
            # Guardamos el nombre
            new_client = Client(
                wa_id=phone_number,
                salon_id=salon_id,
                name=message_text.strip()
            )
            self.db.add(new_client)
            # Importante: Hacer commit o flush para que se guarde el cliente
            await self.db.commit() 
            
            await self.session_manager.update_step(session, "IDLE")
            return f"¡Mucho gusto, {message_text}! Ya te registré. ¿En qué puedo ayudarte hoy?"

        # 3. Si no estamos esperando un dato específico, analizamos intención
        analysis = await self.llm.analyze_message(message_text)
        intent = analysis.get("intent")

        if intent == "GREETING":
            if client and client.name:
                response = f"¡Hola de nuevo, {client.name}! ✨ Qué gusto saludarte. ¿Te gustaría agendar una cita?"
            else:
                response = "¡Hola! Bienvenido a nuestro salón. ✨ Veo que es tu primera vez por aquí, ¿cuál es tu nombre para registrarte?"
                # Cambiamos el estado para esperar el nombre
                await self.session_manager.update_step(session, "AWAITING_NAME")
                
        elif session.current_step == "AWAITING_NAME":
                # Le pedimos al LLM que extraiga solo el nombre propio
                name_analysis = await self.llm.analyze_message(
                    f"Extrae solo el nombre de esta frase: '{message_text}'. Si no hay nombre, devuelve 'Desconocido'."
                )
                # Asumiendo que añadimos una entidad 'name' en el prompt del LLM o usamos el intent
                clean_name = name_analysis.get("entities", {}).get("name") or message_text.strip()
                
                # Guardamos en la DB
                new_client = Client(
                    wa_id=phone_number,
                    salon_id=salon_id,
                    name=clean_name
                )
                self.db.add(new_client)
                await self.db.commit() 
                
                await self.session_manager.update_step(session, "IDLE")
                return f"¡Mucho gusto, {clean_name}! Ya te registré. ¿En qué puedo ayudarte hoy?"
            
        elif intent == "BOOK_APPOINTMENT":
            entities = analysis.get("entities", {})
            fecha = entities.get("date") or "algún día"
            response = f"¡Claro! Entiendo que quieres agendar para {fecha}. Déjame revisar disponibilidad..."
            await self.session_manager.update_step(session, "CHECKING_AVAILABILITY", context=entities)
            
        else:
            response = "Lo siento, todavía estoy aprendiendo. ¿Podrías decirme si quieres agendar o cancelar una cita?"

        return response