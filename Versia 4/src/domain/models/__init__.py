"""src/domain/models/__init__.py"""
from src.domain.models.appointment import Appointment
from src.domain.models.time_slot import TimeSlot
from src.domain.models.working_day import WorkingDay

__all__ = ["Appointment", "TimeSlot", "WorkingDay"]
