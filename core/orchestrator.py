from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from core.session import SessionManager
from core.llm import LLMService
from datetime import datetime, timedelta
from services.availability import AvailabilityService
from appointments.create import AppointmentCreator
from appointments.reschedule import AppointmentRescheduler
from appointments.cancel import AppointmentCanceller
from appointments.waitlist import WaitlistManager
from notifications.sender import NotificationSender
import json

from db.models import Appointment, AppointmentStatus, Client, Service, Stylist, Salon, Waitlist, WaitlistRequestType, WaitlistStatus
import zoneinfo

class Orchestrator:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self.session_manager = SessionManager(db_session)
        self.llm = LLMService()
        self.notification_sender = NotificationSender()

    async def handle_message(self, phone_number: str, message_text: str, salon_id: str):
        intent = "UNKNOWN"
        entities = {}
        # 1. Recuperar sesión, cliente y salón (para timezone)
        
        session = await self.session_manager.get_or_create(phone_number, salon_id)
        
        result = await self.db.execute(
            select(Client).where(Client.wa_id == phone_number, Client.salon_id == salon_id)
        )
        client = result.scalars().first()
        
        salon_res = await self.db.execute(select(Salon).where(Salon.id == salon_id))
        salon = salon_res.scalar_one_or_none()
        salon_tz_str = salon.timezone if salon and salon.timezone else "UTC"
        salon_tz = zoneinfo.ZoneInfo(salon_tz_str)

        now = datetime.now(salon_tz)

        # 2. FLUJO DE REGISTRO (Si no existe el cliente)
        if not client:
            # Usamos el LLM para ver si el usuario se está presentando
            analysis = await self.llm.analyze_message(
                message_text=message_text,
                client_name="Nuevo Usuario",
                current_entities={},
                context_services="",
                history="",
                current_step="REGISTRATION",
                salon_timezone=salon_tz_str
            )
            extracted_name = analysis.get("entities", {}).get("name")
            
            if extracted_name:
                # Si la IA logró extraer un nombre propio
                new_client = Client(wa_id=phone_number, salon_id=salon_id, name=extracted_name)
                self.db.add(new_client)
                await self.db.commit()
                # Refrescamos para tener el objeto client disponible para el resto del flujo
                client = new_client
            else:
                # Si no se pudo extraer un nombre, preguntamos amablemente
                return "¡Hola! ✨ Bienvenido. No te tengo en mis registros, ¿cómo te llamas?"


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
        active_appointment = appointment_res.scalars().first()
        if active_appointment:
            print(f"DEBUG: Cita activa encontrada para {phone_number}: {active_appointment.id} ({active_appointment.start_time})")
        else:
            print(f"DEBUG: No se encontró cita activa para {phone_number}")
        # ---------------------------------

        # 3. PREPARAR CONTEXTO Y CATÁLOGO
        # Cargamos lo que el bot ya sabía de mensajes anteriores
        current_context = json.loads(session.context_data) if session.context_data else {}
        
        # Preparamos catálogo y historial para el LLM
        res = await self.db.execute(select(Service).where(Service.salon_id == salon_id, Service.is_active == True))
        db_services = res.scalars().all()
        
        # Agrupamos por categoría
        services_by_cat = {}
        for s in db_services:
            cat = s.category or "Otros"
            if cat not in services_by_cat:
                services_by_cat[cat] = []
            services_by_cat[cat].append(f"{s.name} ({s.duration_minutes} min): ${s.price}")
        
        catalogo_str = ""
        for cat, items in services_by_cat.items():
            catalogo_str += f"\n{cat}:\n" + "\n".join([f"- {i}" for i in items]) + "\n"
        
        history_list = current_context.get("last_messages", [])
        history_list.append({"role": "user", "content": message_text})
        if len(history_list) > 10:
            history_list = history_list[-10:]
            
        history_text = "\n".join([f"{m['role']}: {m['content']}" for m in history_list])

        # 4. ANÁLISIS DEL LLM
        current_entities = {
            "service": current_context.get("service"),
            "datetime_iso": current_context.get("datetime_iso")
        }

        if active_appointment:
            fecha_cita = active_appointment.start_time.astimezone(salon_tz).strftime('%d/%m a las %H:%M')
            history_text += f"\nSYSTEM: El usuario ya tiene una cita agendada para el {fecha_cita}. Si el usuario quiere cambiar de hora o día, es un RESCHEDULE. Si el usuario quiere cancelar su cita, es un CANCEL_APPOINTMENT."

        analysis = await self.llm.analyze_message(
            message_text=message_text,
            client_name=client.name,
            current_entities=current_entities,
            context_services=catalogo_str,
            history=history_text,
            current_step=session.current_step,
            salon_timezone=salon_tz_str
        )

        # 5. Extraer intent y entidades
        intent = analysis.get("intent", "UNKNOWN")
        entities = analysis.get("entities", {})
        response_message = analysis.get("response_message", "Lo siento, hubo un pequeño problema técnico. ¿Me puedes repetir?")

        # --- LÓGICA TWO-PASS PARA DISPONIBILIDAD ---
        dt_iso = entities.get("datetime_iso") or current_context.get("datetime_iso")
        needs_reanalysis = False
        
        if dt_iso:
            try:
                from datetime import timedelta
                
                # 1. Calcular duración primero para usarla en ANY o en específico
                duration = 30
                if current_context.get("service") or entities.get("service"):
                    srv_name = entities.get("service") or current_context.get("service")
                    srv_res = await self.db.execute(select(Service).where(Service.name == srv_name, Service.salon_id == salon_id))
                    srv_obj = srv_res.scalars().first()
                    if srv_obj:
                        duration = srv_obj.duration_minutes

                # --- LÓGICA DE AGENDAMIENTO AUTOMÁTICO (ANY) ---
                if dt_iso == "ANY":
                    # Buscamos desde "ahora" (o mañana si ya cerraron)
                    search_start = now
                    if now.hour >= 17: # Si ya es tarde, buscar desde mañana a las 9am
                        search_start = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0)
                    
                    # Buscamos en los próximos 3 días
                    found_slot = None
                    for i in range(3):
                        day_to_check = search_start + timedelta(days=i)
                        exclude_id = active_appointment.id if active_appointment else None; slots = await AvailabilityService.get_available_slots(self.db, str(salon_id), day_to_check.date(), duration, exclude_appointment_id=exclude_id)
                        if slots:
                            # Tomar el primero disponible que sea después de search_start
                            for s in slots:
                                # Parsing robusto de "HH:MM AM/PM"
                                time_part, period = s.split(' ')
                                h, m = map(int, time_part.split(':'))
                                if period == 'PM' and h < 12:
                                    h += 12
                                elif period == 'AM' and h == 12:
                                    h = 0
                                
                                slot_dt = day_to_check.replace(hour=h, minute=m, second=0, microsecond=0)

                                if slot_dt > now:
                                    found_slot = slot_dt
                                    break
                        if found_slot: break
                    
                    if found_slot:
                        entities["datetime_iso"] = found_slot.isoformat()
                        dt_iso = entities["datetime_iso"]
                        # Forzamos un mensaje amigable sugiriendo este horario
                        fecha_sug = found_slot.strftime('%d/%m a las %H:%M')
                        history_text += f"\nSYSTEM: El usuario pidió el más cercano. Sugerimos {fecha_sug}. Pregúntale si le va bien ese horario."
                        needs_reanalysis = True
                    else:
                        history_text += f"\nSYSTEM: No hay huecos disponibles en los próximos 3 días. Infórmale al usuario y dile que lo pondrás en lista de espera si lo desea."
                        # Agregamos a lista de espera automáticamente si pidió ANY
                        waitlist_manager = WaitlistManager(self.db)
                        srv_id = srv_obj.id if 'srv_obj' in locals() and srv_obj else None
                        await waitlist_manager.add_to_waitlist(
                            salon_id=salon_id,
                            client_id=str(client.id),
                            request_type=WaitlistRequestType.FLEXIBLE,
                            preferred_service_id=srv_id
                        )
                        needs_reanalysis = True
                
                # --- LÓGICA NORMAL ---
                else:
                    start_dt = datetime.fromisoformat(dt_iso)
                    if start_dt.tzinfo is None:
                        start_dt = start_dt.replace(tzinfo=salon_tz)
                    
                    if intent == "CHECK_AVAILABILITY":
                        slots = await AvailabilityService.get_available_slots(self.db, str(salon_id), start_dt.date(), duration)
                        history_text += f"\nSYSTEM: El usuario pregunta disponibilidad para {start_dt.date()}. Los horarios libres son: {', '.join(slots) if slots else 'Ninguno'}. Infórmale."
                        needs_reanalysis = True
                    else:
                        # Validar disponibilidad real en BD si está agendando o reprogramando
                        exclude_id = active_appointment.id if active_appointment else None
                        is_ok, msg = await AvailabilityService.check_availability(self.db, str(salon_id), start_dt, duration, exclude_appointment_id=exclude_id)
                        
                        if not is_ok:
                            slots = await AvailabilityService.get_available_slots(self.db, str(salon_id), start_dt.date(), duration)
                            history_text += f"\nSYSTEM: La hora solicitada ({start_dt.strftime('%H:%M')}) no es válida o ya está ocupada: {msg}. Los horarios libres para ese día son: {', '.join(slots) if slots else 'Ninguno'}. Pídele que elija uno de esos horarios."
                            entities["datetime_iso"] = None
                            needs_reanalysis = True


            except Exception as e:
                print(f"Error parseando fecha para availability: {e}")
                
        if needs_reanalysis:
            analysis = await self.llm.analyze_message(
                message_text=message_text,
                client_name=client.name,
                current_entities=current_entities,
                context_services=catalogo_str,
                history=history_text,
                current_step=session.current_step,
                salon_timezone=salon_tz_str
            )
            intent = analysis.get("intent", intent)
            entities = analysis.get("entities", entities)
            response_message = analysis.get("response_message", response_message)
        # -------------------------------------------

        # 6. Actualizar Contexto con nuevas entidades encontradas
        if entities.get("service"):
            current_context["service"] = entities["service"]
        
        if entities.get("datetime_iso"):
            # Si la IA envía "ANY" pero ya tenemos una fecha real en el contexto, NO la sobreescribimos
            if entities["datetime_iso"] == "ANY" and current_context.get("datetime_iso") and current_context["datetime_iso"] != "ANY":
                pass 
            else:
                current_context["datetime_iso"] = entities["datetime_iso"]


        # Si es RESCHEDULE y no tenemos servicio en el contexto, lo tomamos de la cita activa
        if intent == "RESCHEDULE" and not current_context.get("service") and active_appointment:
            current_context["service"] = active_appointment.service_name

        # Si el intent es BOOK_APPOINTMENT o RESCHEDULE y ya tenemos ambas cosas, pasamos a CONFIRMING
        if intent in ["BOOK_APPOINTMENT", "RESCHEDULE"] and current_context.get("service") and current_context.get("datetime_iso"):
            await self.session_manager.update_step(session, "CONFIRMING_APPOINTMENT")
        
        # Si el intent es CANCEL_APPOINTMENT y tenemos cita activa, pasamos a CONFIRMING_CANCELLATION
        if intent == "CANCEL_APPOINTMENT" and active_appointment:
            await self.session_manager.update_step(session, "CONFIRMING_CANCELLATION")

        # 7. Ejecutar acción de CONFIRM o DECLINE si aplica
        if intent == "DECLINE":
            print(f"DEBUG: Intent DECLINE detectado. Reseteando sesión a IDLE.")
            if session.current_step == "CONFIRMING_WAITLIST":
                # Marcar en lista de espera como rechazado
                try:
                    is_move_up = current_context.get("is_move_up")
                    move_up_id = current_context.get("move_up_appointment_id")
                    
                    if is_move_up and move_up_id:
                        # Si rechazó un ADELANTO, lo marcamos como NO flexible para no volver a preguntarle
                        await self.db.execute(
                            update(Appointment)
                            .where(Appointment.id == move_up_id)
                            .values(is_flexible=False)
                        )
                        print(f"DEBUG: Cliente rechazó adelanto. Cita {move_up_id} marcada como NO flexible.")
                    
                    waitlist_id = current_context.get("waitlist_id")
                    if waitlist_id:
                        await self.db.execute(
                            update(Waitlist)
                            .where(Waitlist.id == waitlist_id)
                            .values(status=WaitlistStatus.REJECTED, rejection_count=Waitlist.rejection_count + 1)
                        )
                except Exception as e:
                    print(f"Error actualizando waitlist/adelanto en DECLINE: {e}")
            
            await self.session_manager.update_step(session, "IDLE")
            current_context["service"] = None
            current_context["datetime_iso"] = None

        # Si el intent es CONFIRM (o CANCEL_APPOINTMENT pero ya estábamos confirmando)
        if intent == "CONFIRM" or (intent == "CANCEL_APPOINTMENT" and session.current_step == "CONFIRMING_CANCELLATION"):
            print(f"DEBUG: Ejecutando confirmación. Intent: {intent}, Step actual: {session.current_step}")
            
            if session.current_step == "CONFIRMING_WAITLIST":
                offered_slot = current_context.get("offered_slot")
                service_name = current_context.get("service")
                waitlist_id = current_context.get("waitlist_id")
                
                if offered_slot and service_name:
                    try:
                        start_dt = datetime.fromisoformat(offered_slot)
                        if start_dt.tzinfo is None:
                            start_dt = start_dt.replace(tzinfo=salon_tz)
                        
                        # AGENDAR DESDE LISTA DE ESPERA O ADELANTAR CITA
                        move_up_id = current_context.get("move_up_appointment_id")
                        if move_up_id:
                            # Es un ADELANTO de una cita existente
                            appt_res = await self.db.execute(select(Appointment).where(Appointment.id == move_up_id))
                            old_appt = appt_res.scalars().first()
                            if old_appt:
                                success, msg = await AppointmentRescheduler.reschedule_appointment(
                                    self.db, old_appt, start_dt, service_name
                                )
                                new_appointment = old_appt
                            else:
                                success, msg = False, "No se encontró la cita original para adelantar."
                        else:
                            # Es una NUEVA CITA desde lista de espera
                            success, msg, new_appointment = await AppointmentCreator.create_appointment(
                                self.db,
                                salon_id=salon_id,
                                client_id=str(client.id),
                                service_name=service_name,
                                start_time=start_dt,
                                is_flexible=True
                            )
                        
                        if success:
                            # Marcar waitlist como completado (o simplemente resetear)
                            if waitlist_id:
                                await self.db.execute(
                                    update(Waitlist)
                                    .where(Waitlist.id == waitlist_id)
                                    .values(status=WaitlistStatus.WAITING) # O COMPLETED si existiera
                                )
                            
                            current_context = {}
                            await self.session_manager.update_step(session, "IDLE", context=current_context)
                            response_message = f"✅ ¡Excelente! Tu cita ha sido agendada para el {start_dt.astimezone(salon_tz).strftime('%d/%m a las %H:%M')}. Nos vemos pronto."
                            
                            # Enviar notificación de confirmación
                            await self.notification_sender.notify_appointment_confirmed(
                                phone_number,
                                service_name,
                                start_dt.astimezone(salon_tz).strftime('%d/%m a las %H:%M')
                            )
                        else:
                            response_message = f"Lo siento, parece que ese horario ya no está disponible: {msg}"
                            await self.session_manager.update_step(session, "IDLE")
                    except Exception as e:
                        print(f"❌ Error al agendar desde waitlist: {e}")
                        response_message = "Hubo un problema técnico al confirmar tu cita de lista de espera."
            
            elif session.current_step == "CONFIRMING_CANCELLATION":
                if active_appointment:
                    try:
                        print(f"DEBUG: Cancelando cita ID: {active_appointment.id}")
                        success, msg = await AppointmentCanceller.cancel_appointment(
                            self.db, active_appointment, trigger_waitlist=True
                        )
                        if success:
                            current_context = {}
                            await self.session_manager.update_step(session, "IDLE", context=current_context)
                            response_message = msg
                            # Enviar notificación al cliente
                            await self.notification_sender.notify_appointment_cancelled(
                                phone_number,
                                active_appointment.start_time.astimezone(salon_tz).strftime('%d/%m a las %H:%M')
                            )
                            print(f"DEBUG: Cita cancelada con éxito.")
                        else:
                            response_message = f"Hubo un problema al cancelar: {msg}"
                    except Exception as e:
                        print(f"❌ Error al cancelar cita: {e}")
                        await self.db.rollback()
                        response_message = "Hubo un problema técnico al intentar cancelar tu cita. ¿Podrías intentarlo de nuevo?"
                else:
                    print(f"DEBUG: No se encontró cita activa para cancelar en step CONFIRMING_CANCELLATION.")
            
            elif session.current_step in ["IDLE", "CONFIRMING_APPOINTMENT"]:
                service_name = current_context.get("service")
                dt_iso = current_context.get("datetime_iso")
                
                if service_name and dt_iso:
                    try:
                        start_dt = datetime.fromisoformat(dt_iso)
                        if start_dt.tzinfo is None:
                            start_dt = start_dt.replace(tzinfo=salon_tz)
                        
                        if active_appointment:
                            # REPROGRAMAR CITA EXISTENTE (Solo una a la vez)
                            success, msg = await AppointmentRescheduler.reschedule_appointment(
                                self.db, active_appointment, start_dt, service_name
                            )
                            if success:
                                current_context = {}
                                await self.session_manager.update_step(session, "IDLE", context=current_context)
                                response_message = msg
                                # Enviar notificación de confirmación
                                await self.notification_sender.notify_appointment_confirmed(
                                    phone_number,
                                    service_name,
                                    start_dt.astimezone(salon_tz).strftime('%d/%m a las %H:%M')
                                )
                            else:
                                current_context["datetime_iso"] = None
                                response_message = msg
                        else:
                            # AGENDAR NUEVA CITA
                            success, msg, new_appointment = await AppointmentCreator.create_appointment(
                                self.db,
                                salon_id=salon_id,
                                client_id=str(client.id),
                                service_name=service_name,
                                start_time=start_dt,
                                is_flexible=(current_context.get("datetime_iso") == "ANY")
                            )
                            if success:
                                current_context = {}
                                await self.session_manager.update_step(session, "IDLE", context=current_context)
                                response_message = msg
                                # Enviar notificación de confirmación
                                await self.notification_sender.notify_appointment_confirmed(
                                    phone_number,
                                    service_name,
                                    start_dt.astimezone(salon_tz).strftime('%d/%m a las %H:%M')
                                )
                            else:
                                current_context["datetime_iso"] = None
                                response_message = msg
                    except Exception as e:
                        print(f"❌ Error al crear/actualizar cita: {e}")
                        await self.db.rollback()
                        response_message = "Hubo un problema técnico al guardar tu cita. ¿Podrías intentarlo de nuevo?"

        # --- GUARDAR HISTORIAL ---
        history_list = current_context.get("last_messages", [])
        history_list.append({"role": "assistant", "content": response_message})
        current_context["last_messages"] = history_list

        session.context_data = json.dumps(current_context)
        await self.db.commit()

        return response_message