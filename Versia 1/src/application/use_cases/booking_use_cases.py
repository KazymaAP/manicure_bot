"""
src/application/use_cases/booking_use_cases.py — Use Cases для записи.

FIXED H-06: реализованы базовые Use Cases как тонкий оркестрирующий слой
между хендлерами (Presentation) и сервисами (Application).

Преимущества Use Cases:
- Инкапсулируют полный бизнес-сценарий (включая уведомления, планирование напоминаний)
- Хендлеры становятся тоньше и не зависят от деталей сервисов
- Упрощают тестирование: каждый Use Case тестируется изолированно
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.application.dto.booking_dto import BookingResultDTO, CreateBookingDTO
from src.domain.models.appointment import Appointment

if TYPE_CHECKING:
    from src.application.services.appointment_service import AppointmentService
    from src.application.services.notification_service import NotificationService
    from src.application.services.reminder_service import ReminderService
    from src.config.settings import Settings

logger = logging.getLogger(__name__)


class CreateBookingUseCase:
    """Use Case создания новой записи.

    Оркестрирует:
    1. Создание записи через AppointmentService
    2. Уведомление администратора
    3. Планирование напоминания клиенту
    """

    def __init__(
        self,
        appointment_service: AppointmentService,
        notification_service: NotificationService,
        reminder_service: ReminderService,
        settings: Settings,
    ) -> None:
        self._appointment_service = appointment_service
        self._notification_service = notification_service
        self._reminder_service = reminder_service
        self._settings = settings

    def execute(self, dto: CreateBookingDTO) -> BookingResultDTO:
        """Выполняет создание записи.

        Args:
            dto: DTO с данными записи.

        Returns:
            BookingResultDTO с ID созданной записи.

        Raises:
            SlotAlreadyBookedError: Если слот уже занят.
            MaxAppointmentsReachedError: Если превышен лимит записей.
            BlacklistedUserError: Если пользователь в чёрном списке.
        """
        return self._appointment_service.create_booking(dto)

    async def execute_and_notify(self, dto: CreateBookingDTO) -> BookingResultDTO:
        """Выполняет создание записи, отправляет уведомления и планирует напоминание.

        Удобный метод для использования в хендлерах — объединяет все шаги.

        Args:
            dto: DTO с данными записи.

        Returns:
            BookingResultDTO с ID созданной записи.
        """
        import asyncio

        result = await asyncio.to_thread(self._appointment_service.create_booking, dto)

        # Уведомляем администратора
        try:
            await self._notification_service.notify_admin_new_booking(result.appointment_id)
        except Exception as exc:
            logger.warning("Failed to notify admin about new booking #%s: %s", result.appointment_id, exc)

        # Планируем напоминание
        try:
            self._reminder_service.schedule_reminder(
                appointment_id=result.appointment_id,
                user_id=dto.user_id,
                date_str=dto.date,
                time_str=dto.time,
                timezone_str=self._settings.timezone,
            )
        except Exception as exc:
            logger.warning("Failed to schedule reminder for booking #%s: %s", result.appointment_id, exc)

        return result


class CancelBookingUseCase:
    """Use Case отмены записи клиентом.

    Оркестрирует:
    1. Отмену записи через AppointmentService
    2. Уведомление администратора
    3. Отмену запланированного напоминания
    """

    def __init__(
        self,
        appointment_service: AppointmentService,
        notification_service: NotificationService,
        reminder_service: ReminderService,
    ) -> None:
        self._appointment_service = appointment_service
        self._notification_service = notification_service
        self._reminder_service = reminder_service

    async def execute(self, appointment_id: int, user_id: int) -> Appointment | None:
        """Выполняет отмену записи.

        Args:
            appointment_id: ID записи.
            user_id: Telegram ID пользователя (для проверки владельца).

        Returns:
            Отменённый объект Appointment или None.

        Raises:
            AppointmentNotFoundError: Если запись не найдена.
            AppointmentAlreadyCancelledError: Если запись уже отменена.
        """
        import asyncio

        appt = await asyncio.to_thread(
            self._appointment_service.cancel_appointment,
            appointment_id,
            user_id,
        )

        # Уведомляем администратора
        try:
            await self._notification_service.notify_admin_cancellation(appointment_id)
        except Exception as exc:
            logger.warning("Failed to notify admin about cancellation #%s: %s", appointment_id, exc)

        # Отменяем напоминание
        try:
            self._reminder_service.cancel_reminder(appointment_id)
        except Exception as exc:
            logger.warning("Failed to cancel reminder for #%s: %s", appointment_id, exc)

        return appt


class GetUserAppointmentsUseCase:
    """Use Case получения активных записей пользователя.

    Простой фасад над AppointmentService для единообразия
    архитектурного слоя Use Cases.
    """

    def __init__(self, appointment_service: AppointmentService) -> None:
        self._appointment_service = appointment_service

    async def execute(self, user_id: int) -> list[Appointment]:
        """Возвращает активные записи пользователя.

        Args:
            user_id: Telegram ID пользователя.

        Returns:
            Список активных записей.
        """
        import asyncio
        return await asyncio.to_thread(
            self._appointment_service.get_user_appointments,
            user_id,
        )
