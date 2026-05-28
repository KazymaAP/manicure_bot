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
from typing import Optional

from src.domain.models.appointment import Appointment
from src.domain.exceptions import (
    AppointmentNotFoundError,
    AppointmentAlreadyExistsError,
    SlotAlreadyBookedError,
)
from src.application.dto.booking_dto import CreateBookingDTO, BookingResultDTO
from src.infrastructure.repositories.appointment_repository import AppointmentRepository
from src.infrastructure.repositories.schedule_repository import ScheduleRepository

logger = logging.getLogger(__name__)


class AppointmentService:
    """Сервис управления записями клиентов.

    Инкапсулирует бизнес-логику создания, отмены и просмотра записей.
    Все методы синхронные — используют sync sqlite3 через репозитории.
    """

    def __init__(
        self,
        appointment_repo: AppointmentRepository,
        schedule_repo: ScheduleRepository,
        max_per_user: int = 1,
    ) -> None:
        """Инициализирует сервис.

        Args:
            appointment_repo: Репозиторий записей.
            schedule_repo: Репозиторий расписания.
            max_per_user: Максимальное кол-во активных записей у одного клиента.
        """
        self._appointment_repo = appointment_repo
        self._schedule_repo = schedule_repo
        self._max_per_user = max_per_user

    # ─── Создание записи ──────────────────────────────────────────────────

    def create_booking(self, dto: CreateBookingDTO) -> BookingResultDTO:
        """Создаёт новую запись клиента.

        Атомарно проверяет лимит, бронирует слот и сохраняет запись.

        Args:
            dto: DTO с данными для записи.

        Returns:
            BookingResultDTO с результатом операции.

        Raises:
            AppointmentAlreadyExistsError: Если достигнут лимит записей.
            SlotAlreadyBookedError: Если слот занят.
        """
        active_count = self._appointment_repo.count_active_by_user_id(dto.user_id)
        if active_count >= self._max_per_user:
            raise AppointmentAlreadyExistsError(dto.user_id)

        booked = self._schedule_repo.book_slot(dto.date, dto.time)
        if not booked:
            raise SlotAlreadyBookedError(dto.date, dto.time)

        appointment = Appointment(
            user_id=dto.user_id,
            username=dto.username,
            client_name=dto.client_name,
            phone=dto.phone,
            date=dto.date,
            time=dto.time,
            comment=dto.comment,
        )
        appointment_id = self._appointment_repo.create(appointment)
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

    def create_appointment(
        self,
        user_telegram_id: int,
        date_str: str,
        time_str: str,
        client_name: str,
        phone: str,
        comment: Optional[str] = None,
        username: Optional[str] = None,
    ) -> int:
        """Создаёт запись (удобная обёртка над create_booking).

        Args:
            user_telegram_id: Telegram ID клиента.
            date_str: Дата «YYYY-MM-DD».
            time_str: Время «HH:MM».
            client_name: Имя клиента.
            phone: Телефон клиента.
            comment: Опциональный комментарий.
            username: Telegram username клиента.

        Returns:
            ID созданной записи.

        Raises:
            AppointmentAlreadyExistsError: Если достигнут лимит записей.
            SlotAlreadyBookedError: Если слот занят.
        """
        dto = CreateBookingDTO(
            user_id=user_telegram_id,
            username=username,
            client_name=client_name,
            phone=phone,
            date=date_str,
            time=time_str,
            comment=comment,
        )
        result = self.create_booking(dto)
        return result.appointment_id

    # ─── Отмена записи ────────────────────────────────────────────────────

    def cancel_by_user(self, user_id: int) -> Optional[Appointment]:
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

    def cancel_by_id(self, appointment_id: int) -> Optional[Appointment]:
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
            return None
        return self._do_cancel(appointment)

    def cancel_appointment(self, appointment_id: int, user_id: int) -> Optional[Appointment]:
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

    def admin_cancel_appointment(self, appointment_id: int) -> Optional[Appointment]:
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

        # Удаляем запись в БД и освобождаем слот
        self._appointment_repo.cancel(appt_id)
        self._schedule_repo.release_slot(appointment.date, appointment.time)
        appointment.cancel()
        logger.info(
            "Appointment cancelled: id=%s user_id=%s date=%s time=%s",
            appt_id, appointment.user_id, appointment.date, appointment.time,
        )
        return appointment

    # ─── Чтение записей ───────────────────────────────────────────────────

    def get_appointment_by_id(self, appointment_id: int) -> Optional[Appointment]:
        """Возвращает запись по ID.

        Args:
            appointment_id: ID записи.

        Returns:
            Объект Appointment или None.
        """
        return self._appointment_repo.get_by_id(appointment_id)

    def get_active_appointment(self, user_id: int) -> Optional[Appointment]:
        """Возвращает активную запись пользователя."""
        return self._appointment_repo.get_active_by_user_id(user_id)

    def get_user_appointments(self, user_id: int) -> list[Appointment]:
        """Возвращает все активные записи пользователя.

        Args:
            user_id: Telegram ID пользователя.

        Returns:
            Список активных записей.
        """
        active = self._appointment_repo.get_active_by_user_id(user_id)
        return [active] if active else []

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

    def get_statistics(self) -> dict[str, int]:
        """Возвращает статистику по записям через эффективные SQL COUNT.

        Returns:
            Словарь со статистикой: total, confirmed, cancelled, today, week.
        """
        return self._appointment_repo.get_statistics_raw()
