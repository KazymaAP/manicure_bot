"""
src/domain/exceptions/__init__.py
"""
from src.domain.exceptions.base import DomainError, ValidationError
from src.domain.exceptions.appointment import (
    AppointmentNotFoundError,
    AppointmentAlreadyExistsError,
    SlotAlreadyBookedError,
)
from src.domain.exceptions.schedule import (
    WorkingDayAlreadyExistsError,
    WorkingDayNotFoundError,
    PastDateError,
    SlotNotFoundError,
)

__all__ = [
    "DomainError",
    "ValidationError",
    "AppointmentNotFoundError",
    "AppointmentAlreadyExistsError",
    "SlotAlreadyBookedError",
    "WorkingDayAlreadyExistsError",
    "WorkingDayNotFoundError",
    "PastDateError",
    "SlotNotFoundError",
]
