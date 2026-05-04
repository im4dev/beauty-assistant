from datetime import datetime, time, timedelta

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