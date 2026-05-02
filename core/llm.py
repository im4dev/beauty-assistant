from openai import AsyncOpenAI
from core.config import settings
import json

class LLMService:
    def __init__(self):
        # Para usar OpenAI: no pases base_url o usa el de OpenAI
        # Para usar DeepSeek: usa su base_url
        self.client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com" 
        )

    async def analyze_message(self, message_text: str, history: str = ""):
        try:
            response = await self.client.chat.completions.create(
                model="deepseek-chat", # o "gpt-4o" si cambias la configuración
                messages=[
                            {
                                "role": "system", 
                                "content": """Eres un experto extractor de datos. 
                                Responde ÚNICAMENTE en JSON con esta estructura exacta:
                                {
                                    "intent": "GREETING" | "BOOK_APPOINTMENT" | "CANCEL_APPOINTMENT" | "UNKNOWN",
                                    "entities": {"date": "string", "service": "string"}
                                }
                                No traduzcas las llaves. El intent para 'Hola' debe ser 'GREETING'."""
                            },
                            {"role": "user", "content": message_text}
                        ],
                        response_format={"type": "json_object"},
                        temperature=0.1
                    )
            
            # El SDK ya nos da el objeto procesado, mucho más limpio:
            content = response.choices[0].message.content
            return json.loads(content)
            
        except Exception as e:
            print(f"❌ Error en LLM Service: {str(e)}")
            return {"intent": "UNKNOWN", "entities": {}}