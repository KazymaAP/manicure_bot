"""
src/domain/enums/appointment_status.py — Статус записи.
"""
from enum import IntEnum


class AppointmentStatus(IntEnum):
    """Статус записи клиента."""
    ACTIVE = 0
    CANCELLED = 1
