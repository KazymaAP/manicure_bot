"""
src/domain/exceptions/__init__.py — Публичный интерфейс доменных исключений.
"""
from src.domain.exceptions.appointment import (
    AppointmentAlreadyCancelledError,
    AppointmentAlreadyExistsError,
    AppointmentNotFoundError,
    BlacklistedUserError,
    MaxAppointmentsReachedError,
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
    "AppointmentAlreadyCancelledError",
    "AppointmentAlreadyExistsError",
    "MaxAppointmentsReachedError",
    "SlotAlreadyBookedError",
    "BlacklistedUserError",
    "WorkingDayAlreadyExistsError",
    "WorkingDayNotFoundError",
    "PastDateError",
    "SlotNotFoundError",
]
