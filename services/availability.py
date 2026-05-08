from datetime import datetime, time, timedelta, date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import Appointment, AppointmentStatus

class AvailabilityService:
    # Configuración del Salón (Esto luego podría venir de la DB)
    OPENING_TIME = time(9, 0)      # 09:00 AM
    CLOSING_TIME = time(17, 0)     # 05:00 PM
    LUNCH_START = time(12, 0)      # 12:00 PM
    LUNCH_END = time(13, 30)       # 01:30 PM
    
    @classmethod
    def is_within_business_hours(cls, requested_time: datetime, duration_mins: int = 60):
        req_time = requested_time.time()
        req_end = (requested_time + timedelta(minutes=duration_mins)).time()

        # 1. ¿Está dentro del horario general?
        if req_time < cls.OPENING_TIME or req_end > cls.CLOSING_TIME:
            return False, "Lo siento, el salón abre de 9:00 AM a 5:00 PM."

        # 2. ¿Choca con el almuerzo?
        # Verifica si el inicio o el fin de la cita caen dentro del almuerzo
        if not (req_end <= cls.LUNCH_START or req_time >= cls.LUNCH_END):
            return False, "Esa hora coincide con nuestro descanso de almuerzo (12:00 PM a 1:30 PM)."

        # 3. ¿Es demasiado tarde para el servicio? (Tu regla de las 4:30)
        # Si el salón cierra a las 5:00 PM y el servicio dura 60 min, 
        # la última cita debe empezar máximo a las 4:00 PM.
        limit_time = time(16, 30) 
        if req_time > limit_time:
            return False, "La última cita del día es a las 4:30 PM para poder terminar a tiempo."

        return True, "Disponible"

    @classmethod
    async def check_availability(cls, db: AsyncSession, salon_id: str, requested_time: datetime, duration_mins: int = 30, exclude_appointment_id=None):
        # Primero validamos horario de negocio
        is_ok, msg = cls.is_within_business_hours(requested_time, duration_mins)
        if not is_ok:
            return False, msg

        end_time = requested_time + timedelta(minutes=duration_mins)

        # Buscar superposiciones
        query = select(Appointment).where(
            Appointment.salon_id == salon_id,
            Appointment.status == AppointmentStatus.SCHEDULED,
            Appointment.start_time < end_time,
            Appointment.end_time > requested_time
        )
        if exclude_appointment_id:
            query = query.where(Appointment.id != exclude_appointment_id)
            
        res = await db.execute(query)
        overlap = res.scalars().first()

        if overlap:
            return False, "Ese horario ya se encuentra ocupado."
            
        return True, "Disponible"

    @classmethod
    async def get_available_slots(cls, db: AsyncSession, salon_id: str, target_date: date, duration_mins: int = 30, exclude_appointment_id=None):
        from db.models import Salon
        import zoneinfo
        
        salon_res = await db.execute(select(Salon).where(Salon.id == salon_id))
        salon_obj = salon_res.scalars().first()
        salon_tz_str = salon_obj.timezone if salon_obj and salon_obj.timezone else "UTC"
        tz = zoneinfo.ZoneInfo(salon_tz_str)
        now_salon = datetime.now(tz)
        
        available_slots = []
        
        # Generar slots cada 30 min desde OPENING_TIME hasta CLOSING_TIME
        current_dt = datetime.combine(target_date, cls.OPENING_TIME).replace(tzinfo=tz)
        closing_dt = datetime.combine(target_date, cls.CLOSING_TIME).replace(tzinfo=tz)

        # Obtener todas las citas de ese día
        day_start = datetime.combine(target_date, time.min).replace(tzinfo=tz)
        day_end = datetime.combine(target_date, time.max).replace(tzinfo=tz)
        
        query = select(Appointment).where(
            Appointment.salon_id == salon_id,
            Appointment.status == AppointmentStatus.SCHEDULED,
            Appointment.start_time >= day_start,
            Appointment.start_time <= day_end
        )
        
        if exclude_appointment_id:
            query = query.where(Appointment.id != exclude_appointment_id)
            
        res = await db.execute(query)
        appointments = res.scalars().all()

        while current_dt + timedelta(minutes=duration_mins) <= closing_dt:
            is_ok, _ = cls.is_within_business_hours(current_dt, duration_mins)
            
            if is_ok:
                slot_end = current_dt + timedelta(minutes=duration_mins)
                
                # Check overlap against appointments
                overlap = False
                for appt in appointments:
                    # Asyncpg always returns aware datetimes for timezone=True, so no replace needed
                    appt_start = appt.start_time
                    appt_end = appt.end_time
                    
                    if appt_start < slot_end and appt_end > current_dt:
                        overlap = True
                        break
                        
                # Evitamos slots en el pasado si es hoy
                if not overlap and current_dt > now_salon:
                    available_slots.append(current_dt.strftime("%I:%M %p"))

            current_dt += timedelta(minutes=30)
            
        return available_slots