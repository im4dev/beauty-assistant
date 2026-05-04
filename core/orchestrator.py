from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.session import SessionManager
from core.llm import LLMService
from datetime import datetime
from services.availability import AvailabilityService
import json

from db.models import Appointment, AppointmentStatus, Client, Service, Stylist

class Orchestrator:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self.session_manager = SessionManager(db_session)
        self.llm = LLMService()

    async def handle_message(self, phone_number: str, message_text: str, salon_id: str):
        intent = "UNKNOWN"
        entities = {}
        # 1. Recuperar sesión y cliente
        session = await self.session_manager.get_or_create(phone_number, salon_id)
        
        result = await self.db.execute(
            select(Client).where(Client.wa_id == phone_number, Client.salon_id == salon_id)
        )
        client = result.scalar_one_or_none()

        now = datetime.now()

        # 2. FLUJO DE REGISTRO (Si no existe el cliente o estamos esperando el nombre)
        if not client or session.current_step == "AWAITING_NAME":
            if session.current_step != "AWAITING_NAME":
                await self.session_manager.update_step(session, "AWAITING_NAME")
                return "¡Hola! ✨ Bienvenido. No te tengo en mis registros, ¿cómo te llamas?"
            
            # Guardamos el nombre y limpiamos estado
            new_client = Client(wa_id=phone_number, salon_id=salon_id, name=message_text.strip())
            self.db.add(new_client)
            await self.db.commit()
            await self.session_manager.update_step(session, "IDLE")
            return f"¡Mucho gusto, {message_text}! Ya te registré. ¿En qué puedo ayudarte hoy?"

        # --- NEW: SEARCH ACTIVE APPOINTMENT ---
        # Buscamos si existe una cita para este cliente que sea hoy o en el futuro
        appointment_res = await self.db.execute(
            select(Appointment)
            .where( 
                Appointment.client_id == client.id,
                Appointment.start_time >= now, 
                Appointment.status == AppointmentStatus.SCHEDULED
            )
        )
        active_appointment = appointment_res.scalar_one_or_none()
        # ---------------------------------

        # 3. PREPARAR CONTEXTO Y CATÁLOGO
        # Cargamos lo que el bot ya sabía de mensajes anteriores
        current_context = json.loads(session.context_data) if session.context_data else {}
        
        # Preparamos catálogo y historial para el LLM
        res = await self.db.execute(select(Service).where(Service.salon_id == salon_id, Service.is_active == True))
        db_services = res.scalars().all()
        catalogo_str = "\n".join([f"- {s.name}: ${s.price} ({s.duration_minutes} min)" for s in db_services])
        
        history_list = current_context.get("last_messages", [])
        history_text = "\n".join([f"{m['role']}: {m['content']}" for m in history_list])

        # 4. ANÁLISIS DEL LLM
        analysis = await self.llm.analyze_message(
            message_text=message_text,
            context_services=catalogo_str,
            history=history_text,
            current_step=session.current_step
        )

        # 5. Extraer intent y entidades
        intent = analysis.get("intent") or "UNKNOWN"
        entities = analysis.get("entities", {}) or {}

        # 2. Verificación de cita única (se aplica antes de procesar BOOK_APPOINTMENT)
        if intent == "BOOK_APPOINTMENT" and active_appointment:
            fecha_cita = active_appointment.start_time.strftime('%d/%m a las %H:%M')
            return (
                f"¡Hola, {client.name}! Veo que ya tienes una cita agendada para el **{fecha_cita}**. "
                "Por ahora, solo puedes tener una cita activa a la vez. \n\n"
                "¿Te gustaría cancelarla para agendar una nueva o prefieres mantenerla?"
            )

        # 4. CONFIRM: Crear la cita real inmediatamente
        if intent == "CONFIRM":
            if session.current_step != "CONFIRMING_APPOINTMENT":
                return "¿Qué cita quieres confirmar? Primero dime el servicio y la fecha/hora para agendar."

            data = current_context
            service_name = data.get("service")
            dt_iso = data.get("datetime_iso")
            if not service_name or not dt_iso:
                await self.session_manager.update_step(session, "IDLE", context={})
                return "Me faltan datos para agendar. ¿Qué servicio te gustaría y para qué día y hora?"

            try:
                from datetime import timedelta

                start_dt = datetime.fromisoformat(dt_iso)

                service_res = await self.db.execute(
                    select(Service).where(Service.name == service_name, Service.salon_id == salon_id)
                )
                service_obj = service_res.scalar_one_or_none()
                duration = service_obj.duration_minutes if service_obj else 30

                stylist_id = "89274902-6011-4770-b77c-619f71c45686"
                stylist_res = await self.db.execute(
                    select(Stylist).where(Stylist.id == stylist_id, Stylist.salon_id == salon_id)
                )
                stylist_obj = stylist_res.scalar_one_or_none()
                if not stylist_obj:
                    await self.db.rollback()
                    return "No pude asignar estilista para tu cita. ¿Podrías intentarlo de nuevo?"

                new_app = Appointment(
                    salon_id=salon_id,
                    client_id=client.id,
                    stylist_id=stylist_obj.id,
                    service_id=service_obj.id if service_obj else None,
                    service_name=service_name,
                    start_time=start_dt,
                    end_time=start_dt + timedelta(minutes=duration),
                    status=AppointmentStatus.SCHEDULED
                )
                self.db.add(new_app)
                await self.db.commit()

                await self.session_manager.update_step(session, "IDLE", context={})

                return (
                    f"¡Listo, {client.name}! ✅ Tu cita para **{service_name}** ha sido agendada para el "
                    f"{start_dt.strftime('%d/%m a las %H:%M')}. ¡Te esperamos!"
                )
            except Exception as e:
                print(f"❌ Error al crear cita: {e}")
                await self.db.rollback()
                return "Hubo un problema técnico al guardar tu cita. ¿Podrías intentarlo de nuevo?"

        # --- AQUÍ VA EL CAMBIO CLAVE: ACUMULAR ENTIDADES ---
        # Si el LLM encontró algo nuevo, lo sumamos a lo que ya teníamos guardado
        if entities.get("service"):
            current_context["service"] = entities["service"]
        if entities.get("datetime_iso"):
            current_context["datetime_iso"] = entities["datetime_iso"]
        
        # Persistimos el contexto actualizado de inmediato
        session.context_data = json.dumps(current_context)
        await self.db.commit()
        # --------------------------------------------------

        # 5. LÓGICA DE RESPUESTA BASADA EN INTENCIONES
        if intent == "GREETING":
            if any(word in message_text.lower() for word in ["servicios", "precio", "qué haces", "tienes"]):
                return f"¡Hola de nuevo, {client.name}! ✨ Ofrecemos:\n{catalogo_str}\n\n¿Te gustaría agendar?"
            return f"¡Hola de nuevo, {client.name}! ✨ ¿En qué puedo ayudarte?"

        elif intent == "ASK_SERVICES":
            return f"¡Claro! Estos son nuestros servicios:\n{catalogo_str}\n\n¿Cuál te gustaría?"

        elif intent == "BOOK_APPOINTMENT":
            # Usamos los datos ACUMULADOS (current_context), no solo los del último mensaje
            service = current_context.get("service")
            dt_iso = current_context.get("datetime_iso")

            # Caso A: Falta el servicio
            if not service:
                return f"¡Claro! ¿Qué servicio te gustaría realizarte? Tenemos:\n{catalogo_str}"

            # Caso B: Falta la fecha o es inválida
            if not dt_iso or "00:00:00" in dt_iso:
                return f"Perfecto, un {service}. ¿Para qué día y hora? (Atendemos 9am-5pm)"

            # Caso C: Tenemos ambos -> Validar y pedir confirmación
            try:
                requested_dt = datetime.fromisoformat(dt_iso)
                is_ok, error_msg = AvailabilityService.is_within_business_hours(requested_dt)
                
                if not is_ok:
                    # Si la hora está mal, borramos solo la fecha del contexto para que la pida de nuevo
                    current_context["datetime_iso"] = None
                    session.context_data = json.dumps(current_context)
                    await self.db.commit()
                    return f"{error_msg} ¿Podrías elegir otro horario?"

                await self.session_manager.update_step(session, "CONFIRMING_APPOINTMENT")
                return f"Confirmado: {service} para el {requested_dt.strftime('%d/%m a las %H:%M')}. ¿Te lo agendo?"

            except ValueError:
                return "Esa fecha se ve extraña, ¿me la repites?"

        return "Lo siento, no entendí bien. ¿Quieres agendar una cita o ver los servicios?"