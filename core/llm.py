import json
from datetime import datetime
from openai import AsyncOpenAI
from core.config import settings

class LLMService:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com"
        )

    async def analyze_message(
            self,
            message_text: str,
            history: str = "",
            context_services: str = "",
            current_step: str = "IDLE"
            ) -> dict:
        # Obtenemos el momento exacto de la consulta
        now = datetime.now()
        
        # Configuramos el sistema con la fecha actual para cálculos relativos
        prompt = f"""
                Eres un asistente virtual experto para un salón de belleza. Tu objetivo es gestionar citas y resolver dudas de forma amable.
                
                CONTEXTO ACTUAL:
                - Fecha y hora: {now.strftime('%A %d de %B de %Y, %H:%M')}.
                - Estado de la conversación: {current_step}
                
                CATÁLOGO DE SERVICIOS (Usa solo estos nombres exactos):
                {context_services if context_services else "No hay servicios cargados."}

                TAREA:
                Analiza el mensaje del usuario y el historial para devolver un JSON con la intención y entidades.

                INTENCIONES DISPONIBLES:
                - GREETING: Saludos iniciales.
                - BOOK_APPOINTMENT: El usuario quiere agendar una cita o menciona detalles de una (fecha/servicio).
                - ASK_SERVICES: Preguntas sobre qué servicios ofrecen, precios o duración.
                - CONFIRM: El usuario acepta una propuesta o confirma datos (ej: "sí", "dale", "me parece bien", "perfecto").
                - CANCEL: El usuario rechaza o cancela (ej: "no", "mejor no", "ya no quiero").
                - CHITCHAT: Conversación casual o fuera de tema.
                - UNKNOWN: No se entiende la petición.

                REGLAS DE EXTRACCIÓN:
                1. 'service': Debe coincidir EXACTAMENTE con el nombre en el catálogo. Si el usuario dice "pintarme el pelo", mapealo a "Tinte Completo" si existe.
                2. 'datetime_iso': Convierte fechas relativas ("mañana", "el lunes") a formato ISO (YYYY-MM-DD HH:MM:SS).
                3. 'name': Extrae el nombre propio si el usuario se presenta.

                JSON FORMAT:
                {{
                    "intent": "INTENTION_NAME",
                    "entities": {{
                        "datetime_iso": "2026-05-03 15:00:00" | null,
                        "service": "Nombre Exacto" | null,
                        "name": "Nombre" | null
                    }},
                    "reasoning": "Breve explicación de por qué elegiste esta intención"
                }}
            """

        messages = [
                {"role": "system", "content": prompt}
            ]

        # Si hay historial, lo agregamos para que el LLM tenga contexto
        if history:
            messages.append({"role": "system", "content": f"HISTORIAL RECIENTE:\n{history}"})

        messages.append({"role": "user", "content": message_text})

        try:
            response = await self.client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.1
            )
            
            content = response.choices[0].message.content
            print(f"LLM Response: {content}")
            return json.loads(content)
            
        except Exception as e:
            print(f"❌ Error en LLM: {str(e)}")
            return {"intent": "UNKNOWN", "entities": {}}