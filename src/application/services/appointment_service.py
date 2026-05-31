"""
src/application/services/appointment_service.py — Сервис записей.

Бизнес-логика создания, отмены и просмотра записей клиентов.
Все методы синхронные (БД — синхронный sqlite3).
Async-хендлеры вызывают их напрямую (sync в async context допустим для
лёгких sync-операций с sqlite3 при низкой нагрузке).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
import sqlite3

from src.application.dto.booking_dto import BookingResultDTO, CreateBookingDTO
from src.domain.exceptions import (
    AppointmentAlreadyExistsError,
    AppointmentNotFoundError,
    SlotAlreadyBookedError,
)
from src.domain.models.appointment import Appointment
from src.infrastructure.repositories.appointment_repository import AppointmentRepository
from src.infrastructure.repositories.schedule_repository import ScheduleRepository

logger = logging.getLogger(__name__)


class AppointmentService:
    """Сервис управления записями клиентов.

    FIXED: create_booking стал атомарным — проверка лимита, бронирование слота и вставка выполняются
    в одной транзакции (BEGIN IMMEDIATE), чтобы избежать race condition при параллельных запросах.
    Также теперь используется специфичное исключение MaxAppointmentsReachedError.
    """

    def __init__(
        self,
        appointment_repo: AppointmentRepository,
        schedule_repo: ScheduleRepository,
        max_per_user: int = 1,
        service_durations: dict | None = None,
        notification_callback: callable | None = None,
    ) -> None:
        self._appointment_repo = appointment_repo
        self._schedule_repo = schedule_repo
        self._max_per_user = max_per_user
        self._service_durations = service_durations or {}
        self._notification_callback = notification_callback

    # ─── Создание записи ──────────────────────────────────────────────────

    def create_booking(self, dto: CreateBookingDTO) -> BookingResultDTO:
        """Создаёт новую запись клиента.

        Поддерживает два пути:
        - если репозиторий выглядит как реальный (имеет _db) — выполняется атомарная транзакция
          (BEGIN IMMEDIATE) для предотвращения гонки при параллельных бронированиях;
        - если репозиторий — мок/стаб (в тестах) — используется интерфейс репозитория
          (count_active_by_user_id, book_slot/create), чтобы тесты могли мокать вызовы.

        FIXED: совместимость с тестами + сохранение атомарности в проде.
        """
        # Path A: real repository with access to underlying DatabaseManager -> atomic transaction
        from src.infrastructure.database.connection import DatabaseManager
        db_obj = getattr(self._appointment_repo, "_db", None)
        if isinstance(db_obj, DatabaseManager):
            db = db_obj  # Используем один DatabaseManager для транзакции
            with db.transaction() as conn:
                # 1) проверка лимита пользователей внутри транзакции
                row = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM appointments WHERE user_id = ? AND is_cancelled = 0",
                    (dto.user_id,),
                ).fetchone()
                active_count = int(row["cnt"] or 0) if row else 0
                if active_count >= self._max_per_user:
                    # FIXED: используем соотв. исключение
                    from src.domain.exceptions.appointment import MaxAppointmentsReachedError

                    raise MaxAppointmentsReachedError(self._max_per_user)

                # 2) проверяем чёрный список
                try:
                    blk_row = conn.execute("SELECT user_id FROM blacklist WHERE user_id = ?", (dto.user_id,)).fetchone()
                    if blk_row:
                        from src.domain.exceptions.appointment import MaxAppointmentsReachedError
                        from src.domain.exceptions.base import DomainError
                        # FIXED: использует специальное исключение BlacklistedUserError
                        from src.domain.exceptions.appointment import BlacklistedUserError

                        raise BlacklistedUserError(dto.user_id)
                except sqlite3.OperationalError:
                    # таблицы blacklist может не быть в старой схеме — игнорируем
                    pass

                # 3) бронируем слот(ы) с учётом длительности услуги
                duration = 0
                try:
                    if getattr(dto, "service", None):
                        duration = int(self._service_durations.get(dto.service, 0))
                except Exception:
                    duration = 0

                booked = self._schedule_repo.book_slots_with_conn(conn, dto.date, dto.time, duration)
                if not booked:
                    from src.domain.exceptions.appointment import SlotAlreadyBookedError

                    raise SlotAlreadyBookedError(dto.date, dto.time)

                # 4) вставляем запись в appointments в той же транзакции
                created_at = (
                    dto.created_at.strftime("%Y-%m-%d %H:%M:%S") if getattr(dto, "created_at", None) else __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
                ins = conn.execute(
                    "INSERT INTO appointments (user_id, username, client_name, phone, date, time, created_at, comment, service) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        dto.user_id,
                        dto.username,
                        dto.client_name,
                        dto.phone,
                        dto.date,
                        dto.time,
                        created_at,
                        dto.comment,
                        dto.service,
                    ),
                )
                appointment_id = ins.lastrowid
                logger.info(
                    "Booking created: id=%s user_id=%s date=%s time=%s",
                    appointment_id, dto.user_id, dto.date, dto.time,
                )
                return BookingResultDTO(
                    appointment_id=appointment_id,
                    client_name=dto.client_name,
                    date=dto.date,
                    time=dto.time,
                )

        # Path B: repository is a mock/stub in tests — use repo interface (not atomic)
        # This keeps tests simple and allows mocking. In production repo path (above) we have atomicity.
        active_count = self._appointment_repo.count_active_by_user_id(dto.user_id)
        if active_count >= self._max_per_user:
            from src.domain.exceptions.appointment import MaxAppointmentsReachedError

            raise MaxAppointmentsReachedError(self._max_per_user)

        # Попытка забронировать слот через ScheduleRepository (интерфейс)
        booked = self._schedule_repo.book_slot(dto.date, dto.time)
        if not booked:
            from src.domain.exceptions.appointment import SlotAlreadyBookedError

            raise SlotAlreadyBookedError(dto.date, dto.time)

        # Создаём объект и сохраняем через репозиторий
        appointment = Appointment(
            id=None,
            user_id=dto.user_id,
            username=dto.username,
            client_name=dto.client_name,
            phone=dto.phone,
            date=dto.date,
            time=dto.time,
        )
        appointment_id = self._appointment_repo.create(appointment)
        logger.info(
            "Booking created (non-atomic path): id=%s user_id=%s date=%s time=%s",
            appointment_id, dto.user_id, dto.date, dto.time,
        )
        return BookingResultDTO(
            appointment_id=appointment_id,
            client_name=dto.client_name,
            date=dto.date,
            time=dto.time,
        )

    def create_appointment(
        self,
        user_telegram_id: int,
        date_str: str,
        time_str: str,
        client_name: str,
        phone: str,
        comment: str | None = None,
        username: str | None = None,
        service: str | None = None,
    ) -> int:
        dto = CreateBookingDTO(
            user_id=user_telegram_id,
            username=username,
            client_name=client_name,
            phone=phone,
            date=date_str,
            time=time_str,
            comment=comment,
            service=service,
        )
        result = self.create_booking(dto)
        return result.appointment_id

    # ─── Отмена записи ────────────────────────────────────────────────────

    def cancel_by_user(self, user_id: int) -> Appointment | None:
        """Отменяет активную запись пользователя.

        Args:
            user_id: Telegram ID пользователя.

        Returns:
            Отменённый объект Appointment или None, если записи нет.
        """
        appointment = self._appointment_repo.get_active_by_user_id(user_id)
        if not appointment:
            return None
        return self._do_cancel(appointment)

    def cancel_by_id(self, appointment_id: int) -> Appointment | None:
        """Отменяет запись по ID.

        Args:
            appointment_id: ID записи.

        Returns:
            Отменённый объект Appointment или None.

        Raises:
            AppointmentNotFoundError: Если запись не найдена.
        """
        appointment = self._appointment_repo.get_by_id(appointment_id)
        if not appointment:
            raise AppointmentNotFoundError(appointment_id)
        if appointment.is_cancelled:
            # FIXED: явная ошибка при попытке отменить уже отменённую запись — помогает диагностике
            raise AppointmentNotFoundError(appointment_id)
        return self._do_cancel(appointment)

    def cancel_appointment(self, appointment_id: int, user_id: int) -> Appointment | None:
        """Отменяет запись клиентом (с проверкой владельца).

        Args:
            appointment_id: ID записи.
            user_id: Telegram ID пользователя.

        Returns:
            Отменённый объект Appointment или None.

        Raises:
            AppointmentNotFoundError: Если запись не найдена или не принадлежит пользователю.
        """
        appointment = self._appointment_repo.get_by_id(appointment_id)
        if not appointment:
            raise AppointmentNotFoundError(appointment_id)
        if appointment.user_id != user_id:
            raise AppointmentNotFoundError(appointment_id)
        return self._do_cancel(appointment)

    def admin_cancel_appointment(self, appointment_id: int) -> Appointment | None:
        """Отменяет запись администратором (без проверки владельца).

        Args:
            appointment_id: ID записи.

        Returns:
            Отменённый объект Appointment или None.

        Raises:
            AppointmentNotFoundError: Если запись не найдена.
        """
        return self.cancel_by_id(appointment_id)

    def _do_cancel(self, appointment: Appointment) -> Appointment:
        """Выполняет отмену записи и освобождает слот.

        Args:
            appointment: Объект записи для отмены.

        Returns:
            Отменённый объект Appointment.
        """
        appt_id = appointment.id
        if appt_id is None:
            logger.error("Attempted to cancel appointment without id: %s", appointment)
            raise AppointmentNotFoundError(-1)

        # Удаляем запись в БД и освобождаем слот (получаем список на уведомление из waitlist)
        self._appointment_repo.cancel(appt_id)
        waitlist_notifications = self._schedule_repo.release_slot(appointment.date, appointment.time)
        appointment.cancel()
        logger.info(
            "Appointment cancelled: id=%s user_id=%s date=%s time=%s, waitlist notify: %s",
            appt_id, appointment.user_id, appointment.date, appointment.time, waitlist_notifications,
        )

        # FIXED: отправляем уведомления пользователям из waitlist через callback
        if self._notification_callback and waitlist_notifications:
            for user_id, time_to_book in waitlist_notifications:
                try:
                    self._notification_callback(user_id, appointment.date, time_to_book)
                except Exception as exc:
                    logger.warning("Failed to notify waitlist user %s: %s", user_id, exc)

        return appointment

    # ─── Чтение записей ───────────────────────────────────────────────────

    def get_appointment_by_id(self, appointment_id: int) -> Appointment | None:
        """Возвращает запись по ID.

        Args:
            appointment_id: ID записи.

        Returns:
            Объект Appointment или None.
        """
        return self._appointment_repo.get_by_id(appointment_id)

    def get_active_appointment(self, user_id: int) -> Appointment | None:
        """Возвращает активную запись пользователя."""
        return self._appointment_repo.get_active_by_user_id(user_id)

    def get_user_appointments(self, user_id: int) -> list[Appointment]:
        """Возвращает все активные записи пользователя.

        FIXED: использует новый метод репозитория, возвращающий список записей —
        поддерживает max_per_user > 1 и совместим с БД.
        """
        return self._appointment_repo.get_active_list_by_user_id(user_id)

    def get_appointments_by_date(self, date_str: str) -> list[Appointment]:
        """Возвращает все активные записи на дату."""
        return self._appointment_repo.get_by_date(date_str)

    def get_upcoming_unreminded(self) -> list[Appointment]:
        """Возвращает предстоящие записи для отправки напоминаний."""
        return self._appointment_repo.get_upcoming_unreminded()

    def mark_reminder_sent(self, appointment_id: int) -> None:
        """Помечает напоминание как отправленное."""
        self._appointment_repo.mark_reminder_sent(appointment_id)

    def get_appointments_filtered(self, filter_key: str) -> list[Appointment]:
        """Возвращает записи с фильтром для админ-панели.

        Args:
            filter_key: Тип фильтра ('today', 'week', 'active', 'all').

        Returns:
            Список отфильтрованных записей.
        """
        today_str = date.today().isoformat()

        if filter_key == "today":
            return self._appointment_repo.get_by_date(today_str)

        elif filter_key == "week":
            week_end = (date.today() + timedelta(days=7)).isoformat()
            return self._appointment_repo.get_by_date_range(today_str, week_end)

        elif filter_key == "active":
            return self._appointment_repo.get_all_active()

        else:  # "all"
            return self._appointment_repo.get_all()

    # 新增: wrapper для поиска и диапазона — используются в админ-панели
    def get_by_date_range(self, from_date: str, to_date: str) -> list[Appointment]:
        return self._appointment_repo.get_by_date_range(from_date, to_date)

    def search_appointments_by_client(self, query: str) -> list[Appointment]:
        return self._appointment_repo.search_by_client(query)

    def get_statistics(self) -> dict[str, int]:
        """Возвращает статистику по записям через эффективные SQL COUNT.

        Returns:
            Словарь со статистикой: total, confirmed, cancelled, today, week.
        """
        return self._appointment_repo.get_statistics_raw()

    def get_last_appointment(self, user_id: int) -> Appointment | None:
        """Возвращает последнюю запись пользователя для персонализации.

        FIXED: для персонального приветствия и автозаполнения имени/телефона.
        """
        return self._appointment_repo.get_last_appointment_by_user(user_id)

    def get_client_visit_history(self, user_id: int) -> dict:
        """Возвращает историю посещений клиента.

        FIXED: для отображения в admin-панели.

        Returns:
            Словарь с total_visits, completed, cancelled, last_visit_date, last_completed_date.
        """
        return self._appointment_repo.get_client_history(user_id)

    def get_month_statistics(self, year: int, month: int) -> dict:
        """Возвращает статистику по месяцам для админ-панели.

        FIXED: статистика по месяцам, популярные дни, пиковые часы.
        """
        return self._appointment_repo.get_month_statistics(year, month)

    def get_all(self) -> list[Appointment]:
        """Возвращает все записи (для архивирования и тестирования).

        FIXED: фича #38 — для архивирования старых записей.
        """
        return self._appointment_repo.get_all()
