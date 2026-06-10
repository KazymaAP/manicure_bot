"""
src/domain/enums/day_status.py — Статус рабочего дня.
"""
from enum import IntEnum


class DayStatus(IntEnum):
    """Статус рабочего дня."""
    OPEN = 0
    CLOSED = 1
