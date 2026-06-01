"""
src/application/dto/booking_dto.py — Data Transfer Objects.

✅ Из v2_zip + v2_tar: CreateBookingDTO, BookingResultDTO
✅ Улучшения v4: AddWorkingDayDTO, AddSlotDTO, frozen dataclasses для безопасности
FIXED M-07: CreateBookingDTO теперь валидирует формат date (YYYY-MM-DD) и time (HH:MM)
"""
from __future__ import annotations

import re
from dataclasses import dataclass


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


@dataclass(frozen=True, slots=True)
class CreateBookingDTO:
    """DTO для создания записи клиентом.

    FIXED M-07: добавлена валидация форматов date и time в __post_init__ —
    некорректные значения вызовут ValueError с понятным сообщением вместо
    падения глубоко в стеке парсинга.
    """
    user_id: int
    client_name: str
    phone: str
    date: str
    time: str
    username: str | None = None
    comment: str | None = None
    service: str | None = None

    def __post_init__(self) -> None:
        # Валидация формата даты
        if not _DATE_RE.match(self.date):
            raise ValueError(
                f"Invalid date format: {self.date!r}. Expected YYYY-MM-DD (e.g. 2025-07-15)"
            )
        # Базовая проверка корректности самой даты
        try:
            from datetime import date as _date
            _date.fromisoformat(self.date)
        except ValueError:
            raise ValueError(f"Invalid date value: {self.date!r}")

        # Валидация формата времени
        if not _TIME_RE.match(self.time):
            raise ValueError(
                f"Invalid time format: {self.time!r}. Expected HH:MM (e.g. 10:00)"
            )
        h, m = map(int, self.time.split(":"))
        if not (0 <= h < 24 and 0 <= m < 60):
            raise ValueError(
                f"Time value out of range: {self.time!r}. Hours 0-23, minutes 0-59."
            )

        # FIXED C-7: валидация номера телефона на уровне бизнес-логики.
        # Телефон принимается как строка, но должен соответствовать формату.
        # Это предотвращает сохранение произвольных строк (типа "haha_not_a_phone") в БД.
        if self.phone:
            normalized_phone = re.sub(r"[\s\-()]+", "", self.phone)
            if not re.match(r"^\+?[\d]{7,15}$", normalized_phone):
                raise ValueError(
                    f"Invalid phone format: {self.phone!r}. "
                    "Expected format like +79991234567 or 89991234567."
                )


@dataclass(frozen=True, slots=True)
class BookingResultDTO:
    """DTO результата создания записи."""
    appointment_id: int
    client_name: str
    date: str
    time: str


@dataclass(frozen=True, slots=True)
class AddWorkingDayDTO:
    """DTO для добавления рабочего дня."""
    date: str
    default_slots: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AddSlotDTO:
    """DTO для добавления временного слота."""
    date: str
    time: str
