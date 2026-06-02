"""
src/domain/enums/appointment_status.py — Статус записи клиента.

Значения соответствуют полю is_cancelled/status в таблице appointments:
  0 — активная запись
  1 — отменённая запись
  2 — завершённая запись (клиент пришёл)
"""
from __future__ import annotations

import logging
from enum import IntEnum

logger = logging.getLogger(__name__)


class AppointmentStatus(IntEnum):
    """Статус записи клиента."""

    ACTIVE = 0
    CANCELLED = 1
    COMPLETED = 2

    @classmethod
    def from_db_value(cls, value: int | None) -> "AppointmentStatus":
        """Безопасно создаёт статус из значения БД.

        Неизвестные значения возвращают ACTIVE как fallback, что предотвращает
        краш при загрузке записей с нестандартными значениями.

        Args:
            value: Числовое значение из поля БД (None трактуется как 0).

        Returns:
            Соответствующий AppointmentStatus, при неизвестном — ACTIVE.
        """
        if value is None:
            return cls.ACTIVE
        try:
            return cls(int(value))
        except (ValueError, TypeError):
            logger.warning(
                "Unknown AppointmentStatus value %r, falling back to ACTIVE", value
            )
            return cls.ACTIVE

    @property
    def label(self) -> str:
        """Человекочитаемая метка статуса на русском."""
        _labels = {
            AppointmentStatus.ACTIVE: "Активна",
            AppointmentStatus.CANCELLED: "Отменена",
            AppointmentStatus.COMPLETED: "Выполнена",
        }
        return _labels.get(self, self.name)
