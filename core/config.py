from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Entorno
    ENV: str = "development"

    # WhatsApp / Meta
    VERIFY_TOKEN: str           # El token que pusiste en Meta Developers
    APP_SECRET: str = ""        # App Secret de tu app en Meta
    WA_ACCESS_TOKEN: str        # Token de acceso permanente de WhatsApp
    WHATSAPP_PHONE_ID: str 

    # DeepSeek
    DEEPSEEK_API_KEY: str
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # Base de datos
    DATABASE_URL: str = "sqlite+aiosqlite:///./beauty.db"
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = "" 

    # Servidor
    PORT: int = 8000

    # Credenciales del dashboard
    DASHBOARD_USERNAME: str = "admin"
    DASHBOARD_PASSWORD: str = "admin"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()