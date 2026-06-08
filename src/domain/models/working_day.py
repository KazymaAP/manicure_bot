"""
src/domain/models/working_day.py — Доменная модель «Рабочий день».
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.domain.enums import DayStatus


@dataclass(slots=True)
class WorkingDay:
    """Рабочий день мастера.

    Attributes:
        date: Дата «YYYY-MM-DD».
        id: Уникальный идентификатор (None до сохранения).
        status: Статус дня (открыт / закрыт).
    """

    date: str
    id: int | None = field(default=None)
    status: DayStatus = field(default=DayStatus.OPEN)

    @property
    def is_open(self) -> bool:
        """True если день открыт для записи."""
        return self.status == DayStatus.OPEN

    @property
    def is_closed(self) -> bool:
        """True если день закрыт."""
        return self.status == DayStatus.CLOSED

    def close(self) -> None:
        """Закрывает день для записи."""
        self.status = DayStatus.CLOSED

    def open(self) -> None:
        """Открывает день для записи."""
        self.status = DayStatus.OPEN

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> WorkingDay:
        """Создаёт экземпляр из строки БД.

        Args:
            row: Словарь с данными из БД.

        Returns:
            Экземпляр WorkingDay.
        """
        return cls(
            id=row["id"],
            date=row["date"],
            status=DayStatus(row.get("is_closed", 0)),
        )

    def to_dict(self) -> dict[str, Any]:
        """Сериализует объект в словарь."""
        return {
            "id": self.id,
            "date": self.date,
            "is_closed": int(self.status),
        }
