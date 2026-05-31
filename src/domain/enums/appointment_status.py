"""
src/domain/enums/appointment_status.py — Статус записи.

FIXED MED-06: добавлен COMPLETED = 2 и защитный метод from_db_value() для безопасной
загрузки из БД. Ранее AppointmentStatus(row["is_cancelled"]) с неизвестным значением
вызывал ValueError и крашил загрузку записей.
"""
from enum import IntEnum


class AppointmentStatus(IntEnum):
    """Статус записи клиента.

    Значения соответствуют полю is_cancelled в таблице appointments:
      0 — активная запись
      1 — отменённая запись
      2 — завершённая запись (FIXED MED-06: добавлено для расширяемости)
    """
    ACTIVE = 0
    CANCELLED = 1
    COMPLETED = 2  # FIXED MED-06: добавлено для поддержки будущих статусов

    @classmethod
    def from_db_value(cls, value: int) -> "AppointmentStatus":
        """Безопасно создаёт статус из значения БД.

        FIXED MED-06: вместо AppointmentStatus(value) напрямую (что падает при неизвестном
        значении) используем этот метод. Неизвестные значения возвращают ACTIVE как fallback,
        что предотвращает краш при загрузке записей с нестандартными значениями is_cancelled.

        Args:
            value: Числовое значение из поля is_cancelled в БД.

        Returns:
            Соответствующий AppointmentStatus, при неизвестном значении — ACTIVE.
        """
        try:
            return cls(value)
        except ValueError:
            import logging
            logging.getLogger(__name__).warning(
                "Unknown AppointmentStatus value %r, falling back to ACTIVE", value
            )
            return cls.ACTIVE
