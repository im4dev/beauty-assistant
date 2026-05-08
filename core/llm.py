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
            client_name: str,
            current_entities: dict,
            history: str = "",
            context_services: str = "",
            current_step: str = "IDLE",
            salon_timezone: str = "UTC"
            ) -> dict:
        # Obtenemos el momento exacto de la consulta
        import zoneinfo
        tz = zoneinfo.ZoneInfo(salon_timezone)
        now = datetime.now(tz)
        
        # Configuramos el sistema con la fecha actual para cálculos relativos
        prompt = f"""
                Eres un asistente virtual experto para un salón de belleza. Tu objetivo es gestionar citas y resolver dudas de forma amable.
                
                CONTEXTO ACTUAL:
                - Fecha y hora actual: {now.strftime('%A %d de %B de %Y, %H:%M')}.
                - Cliente: {client_name}
                - Estado de la conversación: {current_step}
                - Datos recolectados hasta ahora para la cita: {json.dumps(current_entities)}
                
                CATÁLOGO DE SERVICIOS (Usa solo estos nombres exactos):
                {context_services if context_services else "No hay servicios cargados."}

                REGLAS DEL NEGOCIO:
                - Horario de atención: 9am a 5pm.
                - Si el usuario pide un horario fuera de atención, indícale amablemente el horario válido y NO llenes el campo datetime_iso.
                - Si el usuario quiere agendar (BOOK_APPOINTMENT) y falta el servicio o la fecha/hora, pregúntale por los datos faltantes en tu respuesta.
                - Si ya tienes el servicio y la fecha/hora (datetime_iso), pídele explícitamente que confirme la cita.
                - Si el usuario quiere cancelar su cita (CANCEL_APPOINTMENT), pídele explícitamente que confirme que desea cancelarla. Si el usuario acepta (ej: "sí", "adelante"), usa el intent CONFIRM.
                - Si el usuario pregunta por disponibilidad (CHECK_AVAILABILITY), el historial te indicará los horarios libres, menciónalos al usuario.

                TAREA:
                Analiza el mensaje del usuario y el historial. Tu respuesta debe guiar la conversación y generar el mensaje exacto que se le enviará al usuario.

                INTENCIONES DISPONIBLES:
                - GREETING: Saludos iniciales.
                - BOOK_APPOINTMENT: El usuario quiere agendar una cita nueva.
                - RESCHEDULE: El usuario quiere cambiar la fecha u hora de su cita actual.
                - CANCEL_APPOINTMENT: El usuario quiere cancelar una cita que ya tiene agendada.
                - CHECK_AVAILABILITY: El usuario pregunta qué horas o días están disponibles.
                - ASK_SERVICES: Preguntas sobre qué servicios ofrecen, precios o duración (en caso de haber muchos servicios de distintas categorias, ofrece la categoria y luego los servicios de cada una).
                - CONFIRM: El usuario acepta una propuesta o confirma datos (ej: "sí", "dale", "me parece bien", "perfecto", "agendala", "cámbiala").
                - DECLINE: El usuario rechaza una propuesta, dice que no a algo que preguntaste o quiere abortar el proceso actual (ej: "no", "mejor no", "ahora no", "ya no quiero agendar").
                - CHITCHAT: Conversación casual o fuera de tema.
                - UNKNOWN: No se entiende la petición.

                REGLAS DE EXTRACCIÓN:
                1. 'service': Debe coincidir EXACTAMENTE con el nombre en el catálogo. Si el usuario dice "pintarme el pelo", mapealo a "Tinte Completo" si existe.
                2. 'datetime_iso': Convierte fechas relativas ("mañana", "el lunes") a formato ISO (YYYY-MM-DD HH:MM:SS). NO lo llenes si está fuera del horario de atención. Si el usuario solo menciona un día sin hora, pon "00:00:00" en la hora para extraer la fecha.
                3. 'name': Extrae el nombre propio si el usuario se presenta (ej: "Me llamo Isaias", "Mi nombre es Isaias", "Soy Isaias"), en todos estos casos el nombre es Isaias.

                JSON FORMAT:
                {{
                    "intent": "INTENTION_NAME",
                    "entities": {{
                        "datetime_iso": "2026-05-03 15:00:00" | null,
                        "service": "Nombre Exacto" | null,
                        "name": "Nombre" | null
                    }},
                    "response_message": "El mensaje exacto, natural y amable que se le enviará al usuario respondiendo a su intención actual y solicitando los datos que falten si aplica.",
                    "reasoning": "Breve explicación de por qué elegiste esta intención y respuesta"
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