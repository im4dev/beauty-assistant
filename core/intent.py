"""
Módulo de detección de intención.

Este módulo define las intenciones disponibles y proporciona utilidades
para validar y procesar intenciones detectadas por el LLM.
"""
from enum import Enum
from typing import Literal


class Intent(str, Enum):
    """Intenciones posibles en la conversación"""
    GREETING = "GREETING"
    BOOK_APPOINTMENT = "BOOK_APPOINTMENT"
    RESCHEDULE = "RESCHEDULE"
    CANCEL_APPOINTMENT = "CANCEL_APPOINTMENT"
    CHECK_AVAILABILITY = "CHECK_AVAILABILITY"
    ASK_SERVICES = "ASK_SERVICES"
    CONFIRM = "CONFIRM"
    DECLINE = "DECLINE"
    CHITCHAT = "CHITCHAT"
    UNKNOWN = "UNKNOWN"


class IntentDetector:
    """
    Valida y procesa intenciones detectadas por el LLM.
    
    Nota: La detección real se hace en core/llm.py usando DeepSeek.
    Este módulo proporciona validación y constantes.
    """
    
    @staticmethod
    def is_valid_intent(intent: str) -> bool:
        """Verifica si una intención es válida"""
        return intent in [i.value for i in Intent]
    
    @staticmethod
    def requires_confirmation(intent: str) -> bool:
        """
        Retorna True si la intención requiere confirmación del usuario.
        
        Args:
            intent: La intención a verificar
        
        Returns:
            True si requiere confirmación
        """
        confirmation_required = [
            Intent.BOOK_APPOINTMENT.value,
            Intent.RESCHEDULE.value,
            Intent.CANCEL_APPOINTMENT.value
        ]
        return intent in confirmation_required
    
    @staticmethod
    def is_booking_related(intent: str) -> bool:
        """
        Retorna True si la intención está relacionada con agendar citas.
        
        Args:
            intent: La intención a verificar
        
        Returns:
            True si es relacionada con agendamiento
        """
        booking_related = [
            Intent.BOOK_APPOINTMENT.value,
            Intent.RESCHEDULE.value,
            Intent.CANCEL_APPOINTMENT.value,
            Intent.CHECK_AVAILABILITY.value
        ]
        return intent in booking_related
    
    @staticmethod
    def get_required_entities(intent: str) -> list[str]:
        """
        Retorna las entidades requeridas para cada intención.
        
        Args:
            intent: La intención
        
        Returns:
            Lista de nombres de entidades requeridas
        """
        required = {
            Intent.BOOK_APPOINTMENT.value: ["service", "datetime_iso"],
            Intent.RESCHEDULE.value: ["datetime_iso"],
            Intent.CANCEL_APPOINTMENT.value: [],
            Intent.CHECK_AVAILABILITY.value: ["datetime_iso"],
            Intent.ASK_SERVICES.value: [],
        }
        return required.get(intent, [])
