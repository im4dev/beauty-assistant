import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import SessionState

class SessionManager:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def get_or_create(self, wa_id: str, salon_id: str):
        # Buscamos sesión existente
        result = await self.db.execute(
            select(SessionState).where(SessionState.wa_id == wa_id)
        )
        session_state = result.scalar_one_or_none()

        # Si no existe, la creamos
        if not session_state:
            session_state = SessionState(
                wa_id=wa_id,
                salon_id=salon_id,
                current_step="START",
                context_data="{}"
            )
            self.db.add(session_state)
            await self.db.flush() # Para obtener el objeto listo
        
        return session_state

    async def update_step(self, session_state: SessionState, step: str, context: dict = None):
        session_state.current_step = step
        if context is not None:
            # Mezclamos el contexto nuevo con el anterior
            old_context = json.loads(session_state.context_data)
            old_context.update(context)
            session_state.context_data = json.dumps(old_context)
        
        await self.db.commit()

    async def update_session(self, session, step: str, context: dict = None):
        session.current_step = step
        if context:
            # Recuperamos lo que ya había para no borrarlo
            existing_data = json.loads(session.context_data) if session.context_data else {}
            # Mezclamos con lo nuevo
            existing_data.update(context)
            session.context_data = json.dumps(existing_data)
        
        # ¡VITAL! Sin esto, el cambio solo vive en la memoria de Python
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)