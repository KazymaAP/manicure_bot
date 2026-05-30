"""
src/domain/exceptions/__init__.py
"""
from src.domain.exceptions.appointment import (
    AppointmentAlreadyExistsError,
    AppointmentNotFoundError,
    SlotAlreadyBookedError,
)
from src.domain.exceptions.base import DomainError, ValidationError
from src.domain.exceptions.schedule import (
    PastDateError,
    SlotNotFoundError,
    WorkingDayAlreadyExistsError,
    WorkingDayNotFoundError,
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
