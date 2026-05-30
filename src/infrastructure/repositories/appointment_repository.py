"""
src/infrastructure/repositories/appointment_repository.py — Репозиторий записей.

✅ Из v2_tar: полная реализация с transaction context manager, from_row
✅ Улучшения v4: get_by_user_and_date для проверки дубликатов, count_active_by_user
"""
from __future__ import annotations

import logging
from datetime import datetime

from src.domain.models.appointment import Appointment
from src.infrastructure.database.connection import DatabaseManager
from src.infrastructure.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class AppointmentRepository(BaseRepository):
    """Репозиторий для работы с записями клиентов.

    Инкапсулирует все SQL-запросы к таблице appointments.
    """

    def __init__(self, db: DatabaseManager) -> None:
        super().__init__(db)

    def create(self, appointment: Appointment) -> int:
        """Создаёт новую запись в БД.

        Args:
            appointment: Объект записи для сохранения.

        Returns:
            ID созданной записи.
        """
        created_at = (
            appointment.created_at.strftime("%Y-%m-%d %H:%M:%S")
            if appointment.created_at
            else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        with self._db.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO appointments
                    (user_id, username, client_name, phone, date, time, created_at, comment)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    appointment.user_id,
                    appointment.username,
                    appointment.client_name,
                    appointment.phone,
                    appointment.date,
                    appointment.time,
                    created_at,
                    appointment.comment,
                ),
            )
            return cur.lastrowid

    def get_by_id(self, appointment_id: int) -> Appointment | None:
        """Находит запись по ID.

        Args:
            appointment_id: ID записи.

        Returns:
            Объект Appointment или None.
        """
        with self._db.read_connection() as conn:
            row = conn.execute(
                "SELECT * FROM appointments WHERE id = ?",
                (appointment_id,),
            ).fetchone()
        return Appointment.from_row(dict(row)) if row else None

    def get_active_by_user_id(self, user_id: int) -> Appointment | None:
        """Находит первую активную запись пользователя.

        Args:
            user_id: Telegram ID пользователя.

        Returns:
            Первая активная запись или None.
        """
        with self._db.read_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM appointments
                WHERE user_id = ? AND is_cancelled = 0
                ORDER BY date, time
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        return Appointment.from_row(dict(row)) if row else None

    def count_active_by_user_id(self, user_id: int) -> int:
        """Считает количество активных записей пользователя.

        Args:
            user_id: Telegram ID пользователя.

        Returns:
            Количество активных записей.
        """
        with self._db.read_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM appointments WHERE user_id = ? AND is_cancelled = 0",
                (user_id,),
            ).fetchone()
        return row["cnt"] if row else 0

    def get_by_date(self, date: str) -> list[Appointment]:
        """Возвращает все активные записи на указанную дату.

        Args:
            date: Дата «YYYY-MM-DD».

        Returns:
            Список записей, упорядоченных по времени.
        """
        with self._db.read_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM appointments
                WHERE date = ? AND is_cancelled = 0
                ORDER BY time
                """,
                (date,),
            ).fetchall()
        return [Appointment.from_row(dict(row)) for row in rows]

    def get_upcoming_unreminded(self) -> list[Appointment]:
        """Возвращает предстоящие записи без отправленных напоминаний.

        Returns:
            Список записей, требующих напоминания.
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        with self._db.read_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM appointments
                WHERE is_cancelled = 0
                  AND reminder_sent = 0
                  AND (date || ' ' || time) > ?
                ORDER BY date, time
                """,
                (now_str,),
            ).fetchall()
        return [Appointment.from_row(dict(row)) for row in rows]

    def cancel(self, appointment_id: int) -> bool:
        """Отменяет запись по ID.

        Args:
            appointment_id: ID записи для отмены.

        Returns:
            True если запись успешно отменена.
        """
        with self._db.transaction() as conn:
            cur = conn.execute(
                """
                UPDATE appointments
                SET is_cancelled = 1
                WHERE id = ? AND is_cancelled = 0
                """,
                (appointment_id,),
            )
        return cur.rowcount > 0

    def mark_reminder_sent(self, appointment_id: int) -> None:
        """Помечает напоминание как отправленное.

        Args:
            appointment_id: ID записи.
        """
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE appointments SET reminder_sent = 1 WHERE id = ?",
                (appointment_id,),
            )

    def get_by_date_range(self, from_date: str, to_date: str) -> list[Appointment]:
        """Возвращает все активные записи в диапазоне дат.

        Args:
            from_date: Начало диапазона «YYYY-MM-DD».
            to_date: Конец диапазона «YYYY-MM-DD».

        Returns:
            Список активных записей в диапазоне.
        """
        with self._db.read_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM appointments
                WHERE date BETWEEN ? AND ? AND is_cancelled = 0
                ORDER BY date, time
                """,
                (from_date, to_date),
            ).fetchall()
        return [Appointment.from_row(dict(row)) for row in rows]

    def get_all_active(self) -> list[Appointment]:
        """Возвращает все активные записи.

        Returns:
            Список всех активных записей.
        """
        with self._db.read_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM appointments
                WHERE is_cancelled = 0
                ORDER BY date, time
                """
            ).fetchall()
        return [Appointment.from_row(dict(row)) for row in rows]

    def get_statistics_raw(self) -> dict[str, int]:
        """Возвращает статистику через SQL COUNT — без загрузки всех записей.

        Returns:
            Словарь: total, confirmed, cancelled, today, week.
        """
        from datetime import date as _date
        from datetime import timedelta
        today_str = _date.today().isoformat()
        week_end = (_date.today() + timedelta(days=7)).isoformat()

        with self._db.read_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]
            confirmed = conn.execute(
                "SELECT COUNT(*) FROM appointments WHERE is_cancelled = 0"
            ).fetchone()[0]
            cancelled = conn.execute(
                "SELECT COUNT(*) FROM appointments WHERE is_cancelled = 1"
            ).fetchone()[0]
            today_count = conn.execute(
                "SELECT COUNT(*) FROM appointments WHERE date = ? AND is_cancelled = 0",
                (today_str,),
            ).fetchone()[0]
            week_count = conn.execute(
                """SELECT COUNT(*) FROM appointments
                   WHERE date BETWEEN ? AND ? AND is_cancelled = 0""",
                (today_str, week_end),
            ).fetchone()[0]

        return {
            "total": total,
            "confirmed": confirmed,
            "cancelled": cancelled,
            "today": today_count,
            "week": week_count,
        }

    def get_all(self) -> list[Appointment]:
        """Возвращает все записи (включая отменённые).

        Returns:
            Список всех записей.
        """
        with self._db.read_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM appointments
                ORDER BY date, time
                """
            ).fetchall()
        return [Appointment.from_row(dict(row)) for row in rows]
