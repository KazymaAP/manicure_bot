"""
src/application/dto/booking_dto.py — Data Transfer Objects.

Все DTO используют frozen=True (неизменяемые) и slots=True (экономия памяти).
CreateBookingDTO валидирует форматы date, time и phone при создании.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date as _date, datetime as _datetime

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")
# Разрешённые символы для телефона
_PHONE_CHARS_RE = re.compile(r"^[\d\s\-+(). ]{7,20}$")
_PHONE_DIGITS_RE = re.compile(r"^\+?[\d]{7,15}$")


@dataclass(frozen=True, slots=True)
class CreateBookingDTO:
    """DTO для создания записи клиентом.

    Валидирует форматы date, time и phone при создании объекта,
    чтобы некорректные данные не проникали в бизнес-логику.
    """

    user_id: int
    client_name: str
    phone: str
    date: str
    time: str
    username: str | None = None
    comment: str | None = None
    service: str | None = None
    created_at: _datetime | None = None

    def __post_init__(self) -> None:
        # ── Валидация даты ────────────────────────────────────────────────
        if not _DATE_RE.match(self.date):
            raise ValueError(
                f"Invalid date format: {self.date!r}. Expected YYYY-MM-DD (e.g. 2025-07-15)"
            )
        try:
            _date.fromisoformat(self.date)
        except ValueError as exc:
            raise ValueError(f"Invalid date value: {self.date!r}") from exc

        # ── Валидация времени ─────────────────────────────────────────────
        if not _TIME_RE.match(self.time):
            raise ValueError(
                f"Invalid time format: {self.time!r}. Expected HH:MM (e.g. 10:00)"
            )
        h, m = map(int, self.time.split(":"))
        if not (0 <= h < 24 and 0 <= m < 60):
            raise ValueError(
                f"Time value out of range: {self.time!r}. Hours 0-23, minutes 0-59."
            )

        # ── Валидация имени ───────────────────────────────────────────────
        stripped_name = self.client_name.strip() if self.client_name else ""
        if not stripped_name or len(stripped_name) < 2 or len(stripped_name) > 100:
            raise ValueError(
                f"Invalid client_name: {self.client_name!r}. Must be 2-100 characters."
            )

        # ── Валидация телефона ────────────────────────────────────────────
        if self.phone:
            normalized = re.sub(r"[\s\-()]+", "", self.phone)
            if not _PHONE_DIGITS_RE.match(normalized):
                raise ValueError(
                    f"Invalid phone format: {self.phone!r}. "
                    "Expected format like +79991234567 or 89991234567."
                )

        # ── Валидация комментария ─────────────────────────────────────────
        if self.comment is not None and len(self.comment) > 500:
            raise ValueError(
                f"Comment is too long: {len(self.comment)} chars (max 500)."
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
