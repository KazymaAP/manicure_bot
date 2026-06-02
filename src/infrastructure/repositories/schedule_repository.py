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

    def book_slot(self, date: str, time: str, duration_minutes: int = 0) -> bool:
        """Бронирует слот (один или несколько подряд идущих) атомарно.

        Args:
            date: Дата «YYYY-MM-DD».
            time: Время «HH:MM».
            duration_minutes: если >0 — бронируем несколько подряд идущих слотов суммарной длительностью.

        Returns:
            True если слот(ы) успешно забронированы.
        """
        # Простая реализация: пытаемся забронировать набор слотов в одной транзакции
        with self._db.transaction() as conn:
            return self.book_slots_with_conn(conn, date, time, duration_minutes)

    def book_slots_with_conn(self, conn, date: str, time: str, duration_minutes: int = 0) -> bool:
        """Вспомогательная версия для использования внутри внешней транзакции.

        FIXED: позволяет вызывать бронирование внутри уже открытой транзакции
        (например, в AppointmentService.create_booking), чтобы избежать двойного BEGIN.
        """
        # Если длительность не указана — просто бронируем один слот
        if not duration_minutes:
            cur = conn.execute(
                """
                UPDATE time_slots
                SET is_booked = 1
                WHERE date = ? AND time = ? AND is_booked = 0
                """,
                (date, time),
            )
            return cur.rowcount > 0

        # Иначе — ищем последовательность свободных слотов, начиная с time
        # Получим все слоты для даты упорядоченные по времени
        rows = conn.execute("SELECT time, is_booked FROM time_slots WHERE date = ? ORDER BY time", (date,)).fetchall()
        if not rows:
            return False
        times = [r[0] for r in rows]
        is_booked_flags = {r[0]: r[1] for r in rows}

        try:
            from datetime import datetime
            fmt = "%H:%M"
            datetime.strptime(time, fmt)
        except Exception:
            return False

        # Ищем последовательность слотов, начиная с указанного времени
        needed = []
        accumulated = 0
        idx = None
        for i, t in enumerate(times):
            if t == time:
                idx = i
                break
        if idx is None:
            return False

        for j in range(idx, len(times)):
            t = times[j]
            if is_booked_flags.get(t, 1):  # если забронировано — прерываем
                break
            # Добавим этот слот
            needed.append(t)
            # Вычислим следующую временную метку для оценки длительности
            # Определим интервал между текущим и следующими слотами
            if j + 1 < len(times):
                curr_dt = datetime.strptime(times[j], fmt)
                next_dt = datetime.strptime(times[j + 1], fmt)
                interval = int((next_dt - curr_dt).total_seconds() // 60)
            else:
                # если следующего слота нет — считаем интервал равным duration (остановимся после проверки)
                interval = duration_minutes
            # Полагаем, что слот покрывает интервал до следующего слота
            accumulated += interval
            if accumulated >= duration_minutes:
                break

        # Проверим, накопленная длительность достаточна
        if accumulated < duration_minutes:
            return False

        # Попытка атомарного обновления: установим is_booked=1 для всех нужных времён
        placeholders = ",".join(["?" for _ in needed])
        sql = f"UPDATE time_slots SET is_booked = 1 WHERE date = ? AND time IN ({placeholders}) AND is_booked = 0"
        params = [date] + needed
        cur = conn.execute(sql, params)
        return cur.rowcount == len(needed)


    def release_slot(self, date: str, time: str) -> list[tuple[int, str]]:
        """Освобождает забронированный слот и потенциально соседние забронированные слоты,
        которые были заблокированы для длительной услуги.

        FIXED: освобождаем последовательность забронированных слотов начиная с указанного времени.
        Возвращает список кортежей (user_id, time) из waitlist для уведомления.
        """
        with self._db.transaction() as conn:
            rows = conn.execute("SELECT time, is_booked FROM time_slots WHERE date = ? ORDER BY time", (date,)).fetchall()
            times = [r[0] for r in rows]
            is_booked_flags = {r[0]: r[1] for r in rows}
            try:
                idx = times.index(time)
            except Exception:
                # Если слот не найден — ничего не делаем
                conn.execute("UPDATE time_slots SET is_booked = 0 WHERE date = ? AND time = ?", (date, time))
                return []

            # Освобождаем текущий и последующие подряд идущие забронированные слоты
            to_release = []
            for j in range(idx, len(times)):
                t = times[j]
                if is_booked_flags.get(t, 0):
                    to_release.append(t)
                else:
                    break
            if not to_release:
                return []
            placeholders = ",".join(["?" for _ in to_release])
            sql = f"UPDATE time_slots SET is_booked = 0 WHERE date = ? AND time IN ({placeholders})"
            params = [date] + to_release
            conn.execute(sql, params)

            # FIXED: получаем ближайшего клиента в списке ожидания на эту дату
            waitlist = self.get_waitlist_for_date(date)
            if not waitlist:
                return []
            # Удаляем первого и возвращаем его user_id и первое освобождённое время
            first_entry = waitlist[0]
            self.remove_waitlist_entry(first_entry["id"])
            # Возвращаем кортежи (user_id, time_to_notify) для первого свободного слота
            return [(first_entry["user_id"], to_release[0])]

    # ── Waitlist ─────────────────────────────────────────────────────────
    def join_waitlist(self, user_id: int, date: str) -> bool:
        """Добавляет пользователя в лист ожидания на конкретную дату.

        Возвращает True если добавлено, False если уже в списке.
        """
        from datetime import datetime
        with self._db.transaction() as conn:
            # Проверяем дубликат
            row = conn.execute("SELECT id FROM waitlist WHERE user_id = ? AND date = ?", (user_id, date)).fetchone()
            if row:
                return False
            conn.execute(
                "INSERT INTO waitlist (user_id, date, created_at) VALUES (?, ?, ?)",
                (user_id, date, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            )
        return True

    def get_waitlist_for_date(self, date: str) -> list[dict]:
        """Возвращает список записей в листе ожидания для даты (по порядку добавления)."""
        with self._db.read_connection() as conn:
            rows = conn.execute("SELECT * FROM waitlist WHERE date = ? ORDER BY id", (date,)).fetchall()
        return [dict(r) for r in rows]

    def remove_waitlist_entry(self, entry_id: int) -> None:
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM waitlist WHERE id = ?", (entry_id,))

    # ── Шаблоны расписания ─────────────────────────────────────────
    def save_workday_template(self, name: str, schedule: str) -> int:
        """Сохраняет шаблон рабочих дней.

        FIXED: фича #12 — шаблоны рабочих дней для быстрого открытия.
        """
        with self._db.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO workday_templates (name, slots, created_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                (name, schedule),
            )
        return cur.lastrowid

    def get_workday_templates(self) -> list[dict]:
        """Возвращает все сохранённые шаблоны."""
        with self._db.read_connection() as conn:
            rows = conn.execute(
                "SELECT id, name, slots FROM workday_templates ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_workday_template(self, template_id: int) -> None:
        """Удаляет шаблон по ID."""
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM workday_templates WHERE id = ?", (template_id,))

    def get_workday_template(self, template_id: int) -> dict | None:
        """Возвращает конкретный шаблон.

        FIXED: используется правильное имя колонки `slots` вместо `schedule`.
        """
        with self._db.read_connection() as conn:
            row = conn.execute(
                "SELECT id, name, slots FROM workday_templates WHERE id = ?",
                (template_id,),
            ).fetchone()
        return dict(row) if row else None
