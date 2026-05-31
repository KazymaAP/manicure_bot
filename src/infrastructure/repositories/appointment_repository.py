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

    FIXED: добавлен get_active_list_by_user_id для поддержки MAX_APPOINTMENTS_PER_USER>1;
    оптимизирован get_statistics_raw в один запрос.
    """

    def __init__(self, db: DatabaseManager) -> None:
        super().__init__(db)

    def create(self, appointment: Appointment) -> int:
        created_at = (
            appointment.created_at.strftime("%Y-%m-%d %H:%M:%S")
            if appointment.created_at
            else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        with self._db.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO appointments
                    (user_id, username, client_name, phone, date, time, created_at, comment, service)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    appointment.service,
                ),
            )
            return cur.lastrowid

    def get_by_id(self, appointment_id: int) -> Appointment | None:
        with self._db.read_connection() as conn:
            row = conn.execute(
                "SELECT * FROM appointments WHERE id = ?",
                (appointment_id,),
            ).fetchone()
        return Appointment.from_row(dict(row)) if row else None

    def get_active_by_user_id(self, user_id: int) -> Appointment | None:
        """Возвращает первую активную запись пользователя (не меняется — обратная совместимость)."""
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

    def get_active_list_by_user_id(self, user_id: int) -> list[Appointment]:
        """FIXED: Возвращает все активные записи пользователя (новый метод).

        Обратная совместимость: существующие вызовы get_active_by_user_id остаются.
        """
        with self._db.read_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM appointments
                WHERE user_id = ? AND is_cancelled = 0
                ORDER BY date, time
                """,
                (user_id,),
            ).fetchall()
        return [Appointment.from_row(dict(row)) for row in rows]

    def count_active_by_user_id(self, user_id: int) -> int:
        with self._db.read_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM appointments WHERE user_id = ? AND is_cancelled = 0",
                (user_id,),
            ).fetchone()
        return row["cnt"] if row else 0

    def get_by_date(self, date: str) -> list[Appointment]:
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
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE appointments SET reminder_sent = 1 WHERE id = ?",
                (appointment_id,),
            )

    def get_by_date_range(self, from_date: str, to_date: str) -> list[Appointment]:
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
        """FIXED: объединённые COUNT(*) в одном запросе для эффективности."""
        from datetime import date as _date
        from datetime import timedelta
        today_str = _date.today().isoformat()
        week_end = (_date.today() + timedelta(days=7)).isoformat()

        with self._db.read_connection() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN is_cancelled = 0 THEN 1 ELSE 0 END) as confirmed,
                    SUM(CASE WHEN is_cancelled = 1 THEN 1 ELSE 0 END) as cancelled,
                    SUM(CASE WHEN date = ? AND is_cancelled = 0 THEN 1 ELSE 0 END) as today_count,
                    SUM(CASE WHEN date BETWEEN ? AND ? AND is_cancelled = 0 THEN 1 ELSE 0 END) as week_count
                FROM appointments
                """,
                (today_str, today_str, week_end),
            ).fetchone()

        return {
            "total": int(row["total"] or 0),
            "confirmed": int(row["confirmed"] or 0),
            "cancelled": int(row["cancelled"] or 0),
            "today": int(row["today_count"] or 0),
            "week": int(row["week_count"] or 0),
        }

    def get_all(self) -> list[Appointment]:
        with self._db.read_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM appointments
                ORDER BY date, time
                """
            ).fetchall()
        return [Appointment.from_row(dict(row)) for row in rows]

    def get_by_date_range(self, from_date: str, to_date: str) -> list[Appointment]:
        with self._db.read_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM appointments WHERE date BETWEEN ? AND ? ORDER BY date, time",
                (from_date, to_date),
            ).fetchall()
        return [Appointment.from_row(dict(row)) for row in rows]

    def search_by_client(self, query: str) -> list[Appointment]:
        """Ищет записи по имени клиента или телефону (простое LIKE-поиск)."""
        q = f"%{query}%"
        with self._db.read_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM appointments WHERE client_name LIKE ? OR phone LIKE ? ORDER BY date, time",
                (q, q),
            ).fetchall()
        return [Appointment.from_row(dict(row)) for row in rows]

    def get_last_appointment_by_user(self, user_id: int) -> Appointment | None:
        """Возвращает последнюю активную запись пользователя для персонализации.

        FIXED: для персонального приветствия и автозаполнения данных.
        """
        with self._db.read_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM appointments
                WHERE user_id = ? AND is_cancelled = 0
                ORDER BY date DESC, time DESC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        return Appointment.from_row(dict(row)) if row else None

    def get_client_history(self, user_id: int) -> dict:
        """Возвращает статистику по клиенту: кол-во посещений, последний визит, отмены.

        FIXED: для отображения в admin-панели истории клиента.
        """
        with self._db.read_connection() as conn:
            stats = conn.execute(
                """
                SELECT
                    COUNT(*) as total_visits,
                    COUNT(CASE WHEN date < date('now') AND is_cancelled = 0 THEN 1 END) as completed,
                    COUNT(CASE WHEN is_cancelled = 1 THEN 1 END) as cancelled,
                    MAX(date) as last_visit_date,
                    MAX(CASE WHEN date < date('now') AND is_cancelled = 0 THEN date END) as last_completed_date
                FROM appointments
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
        return dict(stats) if stats else {
            "total_visits": 0,
            "completed": 0,
            "cancelled": 0,
            "last_visit_date": None,
            "last_completed_date": None,
        }

    def get_by_date(self, date_str: str) -> list[Appointment]:
        """Возвращает все активные записи на конкретную дату."""
        with self._db.read_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM appointments WHERE date = ? AND is_cancelled = 0 ORDER BY time",
                (date_str,),
            ).fetchall()
        return [Appointment.from_row(dict(row)) for row in rows]

    def get_month_statistics(self, year: int, month: int) -> dict:
        """Возвращает статистику по месяцам для админ-панели.

        FIXED: статистика по месяцам, популярные дни, пиковые часы.
        """
        with self._db.read_connection() as conn:
            # Статистика по месяцу
            month_stats = conn.execute(
                """
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN is_cancelled = 0 THEN 1 END) as confirmed,
                    COUNT(CASE WHEN is_cancelled = 1 THEN 1 END) as cancelled
                FROM appointments
                WHERE strftime('%Y', date) = ? AND strftime('%m', date) = ?
                """,
                (f"{year:04d}", f"{month:02d}"),
            ).fetchone()
            
            # Популярные дни недели
            weekday_stats = conn.execute(
                """
                SELECT
                    strftime('%w', date) as weekday,
                    COUNT(*) as count
                FROM appointments
                WHERE strftime('%Y', date) = ? AND strftime('%m', date) = ? AND is_cancelled = 0
                GROUP BY weekday
                ORDER BY count DESC
                """,
                (f"{year:04d}", f"{month:02d}"),
            ).fetchall()
            
            # Пиковые часы
            peak_hours = conn.execute(
                """
                SELECT
                    substr(time, 1, 2) as hour,
                    COUNT(*) as count
                FROM appointments
                WHERE strftime('%Y', date) = ? AND strftime('%m', date) = ? AND is_cancelled = 0
                GROUP BY hour
                ORDER BY count DESC
                LIMIT 5
                """,
                (f"{year:04d}", f"{month:02d}"),
            ).fetchall()
        
        return {
            "total": dict(month_stats)["total"] if month_stats else 0,
            "confirmed": dict(month_stats)["confirmed"] if month_stats else 0,
            "cancelled": dict(month_stats)["cancelled"] if month_stats else 0,
            "popular_weekdays": [dict(row) for row in weekday_stats],
            "peak_hours": [dict(row) for row in peak_hours],
        }
