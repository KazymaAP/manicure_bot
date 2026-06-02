"""
src/domain/exceptions/schedule.py — Исключения для расписания.
"""
from __future__ import annotations

from src.domain.exceptions.base import DomainError


class WorkingDayAlreadyExistsError(DomainError):
    """Рабочий день с такой датой уже существует."""

    def __init__(self, date: str) -> None:
        super().__init__(f"Working day {date} already exists")
        self.date = date


class WorkingDayNotFoundError(DomainError):
    """Рабочий день не найден."""

    def __init__(self, date: str) -> None:
        super().__init__(f"Working day {date} not found")
        self.date = date


class PastDateError(DomainError):
    """Попытка добавить прошедшую дату."""

    def __init__(self, date: str) -> None:
        super().__init__(f"Cannot add past date: {date}")
        self.date = date


class SlotNotFoundError(DomainError):
    """Временной слот не найден."""

    def __init__(self, date: str, time: str) -> None:
        super().__init__(f"Slot {date} {time} not found")
        self.date = date
        self.time = time
