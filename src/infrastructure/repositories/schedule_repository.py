"""
src/infrastructure/repositories/schedule_repository.py — Репозиторий расписания.

✅ Из v2_tar: полная реализация с WorkingDay/TimeSlot models
✅ Улучшения v4: delete_working_day + CASCADE, batch slot operations
"""
from __future__ import annotations

import logging
import sqlite3

from src.domain.models.time_slot import TimeSlot
from src.domain.models.working_day import WorkingDay
from src.infrastructure.database.connection import DatabaseManager
from src.infrastructure.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ScheduleRepository(BaseRepository):
    """Репозиторий для работы с расписанием.

    Инкапсулирует все SQL-запросы к таблицам working_days и time_slots.
    """

    def __init__(self, db: DatabaseManager) -> None:
        super().__init__(db)

    # ─── WorkingDay ────────────────────────────────────────────

    def add_working_day(self, date: str, default_slots: list[str]) -> bool:
        """Добавляет рабочий день с набором слотов по умолчанию.

        Args:
            date: Дата «YYYY-MM-DD».
            default_slots: Список времён слотов ['09:00', '10:00', ...].

        Returns:
            True если день успешно добавлен; False если уже существует.
        """
        try:
            with self._db.transaction() as conn:
                conn.execute(
                    "INSERT INTO working_days (date) VALUES (?)",
                    (date,),
                )
                conn.executemany(
                    "INSERT OR IGNORE INTO time_slots (date, time) VALUES (?, ?)",
                    [(date, t) for t in default_slots],
                )
            return True
        except sqlite3.IntegrityError:
            # Рабочий день с такой датой уже существует
            return False
        except Exception as exc:
            logger.error("Unexpected error adding working day %s: %s", date, exc)
            raise

    def get_working_day(self, date: str) -> WorkingDay | None:
        """Находит рабочий день по дате.

        Args:
            date: Дата «YYYY-MM-DD».

        Returns:
            Объект WorkingDay или None.
        """
        with self._db.read_connection() as conn:
            row = conn.execute(
                "SELECT * FROM working_days WHERE date = ?", (date,)
            ).fetchone()
        return WorkingDay.from_row(dict(row)) if row else None

    def get_open_days_in_range(self, from_date: str, to_date: str) -> list[WorkingDay]:
        """Возвращает открытые рабочие дни в диапазоне.

        Args:
            from_date: Начало диапазона «YYYY-MM-DD».
            to_date: Конец диапазона «YYYY-MM-DD».

        Returns:
            Список открытых рабочих дней.
        """
        with self._db.read_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM working_days
                WHERE date BETWEEN ? AND ? AND is_closed = 0
                ORDER BY date
                """,
                (from_date, to_date),
            ).fetchall()
        return [WorkingDay.from_row(dict(row)) for row in rows]

    def get_all_days_in_range(self, from_date: str, to_date: str) -> list[WorkingDay]:
        """Возвращает все рабочие дни в диапазоне (включая закрытые).

        Args:
            from_date: Начало диапазона «YYYY-MM-DD».
            to_date: Конец диапазона «YYYY-MM-DD».

        Returns:
            Список рабочих дней.
        """
        with self._db.read_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM working_days
                WHERE date BETWEEN ? AND ?
                ORDER BY date
                """,
                (from_date, to_date),
            ).fetchall()
        return [WorkingDay.from_row(dict(row)) for row in rows]

    def is_working_day(self, date: str) -> bool:
        """Проверяет, является ли дата открытым рабочим днём.

        Args:
            date: Дата «YYYY-MM-DD».

        Returns:
            True если день открыт.
        """
        with self._db.read_connection() as conn:
            row = conn.execute(
                "SELECT id FROM working_days WHERE date = ? AND is_closed = 0",
                (date,),
            ).fetchone()
        return row is not None

    def set_day_status(self, date: str, is_closed: bool) -> None:
        """Устанавливает статус рабочего дня.

        Args:
            date: Дата «YYYY-MM-DD».
            is_closed: True для закрытия, False для открытия.
        """
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE working_days SET is_closed = ? WHERE date = ?",
                (int(is_closed), date),
            )

    def delete_working_day(self, date: str) -> None:
        """Удаляет рабочий день и все его слоты.

        Args:
            date: Дата «YYYY-MM-DD».
        """
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM time_slots WHERE date = ?", (date,))
            conn.execute("DELETE FROM working_days WHERE date = ?", (date,))

    # ─── TimeSlot ──────────────────────────────────────────────

    def add_time_slot(self, date: str, time: str) -> bool:
        """Добавляет временной слот.

        Args:
            date: Дата слота «YYYY-MM-DD».
            time: Время слота «HH:MM».

        Returns:
            True если слот добавлен; False при ошибке (дубликат).
        """
        try:
            with self._db.transaction() as conn:
                conn.execute(
                    "INSERT INTO time_slots (date, time) VALUES (?, ?)",
                    (date, time),
                )
            return True
        except sqlite3.IntegrityError:
            # Слот с такой датой и временем уже существует
            return False
        except Exception as exc:
            logger.error("Unexpected error adding time slot %s %s: %s", date, time, exc)
            raise

    def delete_time_slot(self, date: str, time: str) -> bool:
        """Удаляет свободный временной слот.

        Args:
            date: Дата слота «YYYY-MM-DD».
            time: Время слота «HH:MM».

        Returns:
            True если слот удалён.
        """
        with self._db.transaction() as conn:
            cur = conn.execute(
                "DELETE FROM time_slots WHERE date = ? AND time = ? AND is_booked = 0",
                (date, time),
            )
        return cur.rowcount > 0

    def get_free_slots(self, date: str) -> list[TimeSlot]:
        """Возвращает свободные слоты для открытого рабочего дня.

        Args:
            date: Дата «YYYY-MM-DD».

        Returns:
            Список свободных слотов, упорядоченных по времени.
        """
        with self._db.read_connection() as conn:
            rows = conn.execute(
                """
                SELECT ts.*
                FROM time_slots ts
                JOIN working_days wd ON wd.date = ts.date
                WHERE ts.date = ? AND ts.is_booked = 0 AND wd.is_closed = 0
                ORDER BY ts.time
                """,
                (date,),
            ).fetchall()
        return [TimeSlot.from_row(dict(row)) for row in rows]

    def get_all_slots(self, date: str) -> list[TimeSlot]:
        """Возвращает все слоты на дату (включая забронированные).

        Args:
            date: Дата «YYYY-MM-DD».

        Returns:
            Список всех слотов.
        """
        with self._db.read_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM time_slots WHERE date = ? ORDER BY time",
                (date,),
            ).fetchall()
        return [TimeSlot.from_row(dict(row)) for row in rows]

    def get_available_dates_in_range(self, from_date: str, to_date: str) -> set[str]:
        """Возвращает множество дат с хотя бы одним свободным слотом в диапазоне (оптимизация N+1).

        Вместо отдельного SELECT для каждой даты, делает один запрос с JOIN.

        Args:
            from_date: Начало диапазона «YYYY-MM-DD».
            to_date: Конец диапазона «YYYY-MM-DD».

        Returns:
            Множество дат «YYYY-MM-DD» с свободными слотами.
        """
        with self._db.read_connection() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT ts.date
                FROM time_slots ts
                JOIN working_days wd ON wd.date = ts.date
                WHERE ts.date BETWEEN ? AND ? AND ts.is_booked = 0 AND wd.is_closed = 0
                """,
                (from_date, to_date),
            ).fetchall()
        return {row[0] for row in rows}

    def book_slot(self, date: str, time: str) -> bool:
        """Бронирует слот атомарно (предотвращает двойное бронирование).

        Args:
            date: Дата «YYYY-MM-DD».
            time: Время «HH:MM».

        Returns:
            True если слот успешно забронирован.
        """
        with self._db.transaction() as conn:
            cur = conn.execute(
                """
                UPDATE time_slots
                SET is_booked = 1
                WHERE date = ? AND time = ? AND is_booked = 0
                """,
                (date, time),
            )
        return cur.rowcount > 0

    def release_slot(self, date: str, time: str) -> None:
        """Освобождает забронированный слот.

        Args:
            date: Дата «YYYY-MM-DD».
            time: Время «HH:MM».
        """
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE time_slots SET is_booked = 0 WHERE date = ? AND time = ?",
                (date, time),
            )
