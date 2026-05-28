"""
src/domain/models/time_slot.py — Доменная модель «Временной слот».
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(slots=True)
class TimeSlot:
    """Временной слот в расписании.

    Attributes:
        date: Дата слота «YYYY-MM-DD».
        time: Время слота «HH:MM».
        id: Уникальный идентификатор (None до сохранения).
        is_booked: Забронирован ли слот.
    """

    date: str
    time: str
    id: Optional[int] = field(default=None)
    is_booked: bool = field(default=False)

    @property
    def is_free(self) -> bool:
        """True если слот свободен."""
        return not self.is_booked

    def book(self) -> None:
        """Бронирует слот."""
        self.is_booked = True

    def release(self) -> None:
        """Освобождает слот."""
        self.is_booked = False

    @classmethod
    def from_row(cls, row: dict) -> "TimeSlot":
        """Создаёт экземпляр из строки БД.

        Args:
            row: Словарь с данными из БД.

        Returns:
            Экземпляр TimeSlot.
        """
        return cls(
            id=row["id"],
            date=row["date"],
            time=row["time"],
            is_booked=bool(row.get("is_booked", 0)),
        )

    def to_dict(self) -> dict:
        """Сериализует объект в словарь."""
        return {
            "id": self.id,
            "date": self.date,
            "time": self.time,
            "is_booked": int(self.is_booked),
        }
