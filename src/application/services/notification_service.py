"""
src/application/services/notification_service.py — Сервис уведомлений.

✅ Из v2_tar: все методы уведомлений + _safe_send
✅ Улучшения v4: notify_admin_cancellation принимает appointment объект напрямую
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram import Bot

from src.infrastructure.repositories.appointment_repository import AppointmentRepository
from src.presentation.formatters.message_formatter import MessageFormatter

logger = logging.getLogger(__name__)


class NotificationService:
    """Сервис отправки уведомлений через Telegram.

    Централизует логику всех уведомлений — клиентам и администратору.
    """

    def __init__(
        self,
        bot: Bot,
        admin_ids: list[int],
        schedule_channel_id: int,
        appointment_repo: AppointmentRepository,
        service_name: str = "маникюр",
    ) -> None:
        """Инициализирует сервис уведомлений.

        Args:
            bot: Экземпляр Telegram бота.
            admin_ids: Telegram IDs администраторов.
            schedule_channel_id: ID канала для публикации расписания.
            appointment_repo: Репозиторий записей.
            service_name: Название услуги для уведомлений.
        """
        self._bot = bot
        self._admin_ids = admin_ids
        self._schedule_channel_id = schedule_channel_id
        self._appointment_repo = appointment_repo
        self._service_name = service_name

    async def notify_admin_new_booking(self, appointment_id: int) -> None:
        """Уведомляет администратора о новой записи.

        Args:
            appointment_id: ID созданной записи.
        """
        import asyncio
        appt = await asyncio.to_thread(self._appointment_repo.get_by_id, appointment_id)
        if not appt:
            logger.warning("Cannot notify admin: appointment #%s not found", appointment_id)
            return

        text = MessageFormatter.notify_admin_new_booking(
            client_name=appt.client_name,
            phone=appt.phone,
            date=appt.date,
            time=appt.time,
            appt_id=appt.id,
            username=appt.username,
            user_id=appt.user_id,
        )
        for admin_id in self._admin_ids:
            await self._safe_send(admin_id, text)

    async def notify_admins_list(self, text: str) -> None:
        """Отправляет текстовое уведомление всем администраторам.

        Args:
            text: Текст сообщения (HTML).
        """
        for admin_id in self._admin_ids:
            await self._safe_send(admin_id, text)

    async def notify_channel_new_booking(self, appointment_id: int) -> None:
        """Публикует информацию о новой записи в канал расписания.

        Args:
            appointment_id: ID созданной записи.
        """
        import asyncio
        appt = await asyncio.to_thread(self._appointment_repo.get_by_id, appointment_id)
        if not appt:
            return

        text = (
            "📌 <b>Запись добавлена в расписание</b>\n\n"
            f"📅 <b>{appt.date}</b> в <b>{appt.time}</b>\n"
            f"👤 {appt.client_name}"
        )
        await self._safe_send(self._schedule_channel_id, text)

    async def notify_admin_cancellation(self, appointment_id: int) -> None:
        """Уведомляет администратора об отмене записи клиентом.

        Args:
            appointment_id: ID отменённой записи.
        """
        import asyncio
        appt = await asyncio.to_thread(self._appointment_repo.get_by_id, appointment_id)
        if not appt:
            return

        text = MessageFormatter.notify_admin_cancellation(
            client_name=appt.client_name,
            date=appt.date,
            time=appt.time,
            phone=appt.phone,
        )
        for admin_id in self._admin_ids:
            await self._safe_send(admin_id, text)

    async def notify_client_booking_confirmed(
        self, user_id: int, date: str, time: str
    ) -> None:
        """Уведомляет клиента о подтверждении записи администратором.

        Args:
            user_id: Telegram ID клиента.
            date: Дата записи.
            time: Время записи.
        """
        text = f"🎉 Ваша запись подтверждена: <b>{date}</b> в <b>{time}</b>"
        await self._safe_send(user_id, text)

    async def notify_client_cancellation_by_admin(
        self, user_id: int, date: str, time: str
    ) -> None:
        """Уведомляет клиента об отмене его записи администратором.

        Args:
            user_id: Telegram ID клиента.
            date: Дата записи.
            time: Время записи.
        """
        text = MessageFormatter.notify_client_cancellation_by_admin(date=date, time=time)
        await self._safe_send(user_id, text)

    async def send_reminder(self, user_id: int, time: str, appointment_id: int) -> bool:
        """Отправляет напоминание о предстоящем визите с кнопками подтверждения/отмены.

        Args:
            user_id: Telegram ID клиента.
            time: Время записи.
            appointment_id: ID записи для пометки.

        Returns:
            True если напоминание успешно отправлено.
        """
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        import asyncio
        # FIXED: используем карточное напоминание с деталями визита и кнопками
        appt = await asyncio.to_thread(self._appointment_repo.get_by_id, appointment_id)
        client_name = appt.client_name if appt else ""
        date = appt.date if appt else ""
        address = getattr(self, "_address", "") or ""
        text = MessageFormatter.reminder_card(client_name=client_name, date=date, time=time, address=address)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Приду", callback_data=f"reminder_yes:{appointment_id}"), InlineKeyboardButton(text="❌ Отменить", callback_data=f"reminder_no:{appointment_id}")]
        ])
        try:
            await self._bot.send_message(user_id, text, parse_mode="HTML", reply_markup=kb)
            await asyncio.to_thread(self._appointment_repo.mark_reminder_sent, appointment_id)
            logger.info(
                "Reminder sent to user %s for appointment #%s",
                user_id, appointment_id,
            )
            return True
        except Exception as exc:
            logger.error("Failed to send reminder to %s: %s", user_id, exc)
            return False

    async def notify_waitlist_slot_available(self, user_id: int, date: str, time: str) -> bool:
        """Уведомляет пользователя из waitlist о доступном слоте.

        FIXED: отправляет клиенту уведомление с кнопкой для быстрого бронирования.

        Args:
            user_id: Telegram ID пользователя из waitlist.
            date: Дата доступного слота.
            time: Время доступного слота.

        Returns:
            True если уведомление отправлено.
        """
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        text = (
            "🔔 <b>Свободное место!</b>\n\n"
            f"📅 <b>{date}</b> в <b>{time}</b>\n"
            "Хотите это время? Нажмите кнопку ниже!"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Забронировать", callback_data=f"waitlist_book:{date}:{time}")]
        ])
        return await self._safe_send_with_markup(user_id, text, kb)

    async def _safe_send_with_markup(
        self,
        chat_id: int,
        text: str,
        markup: object | None = None,
    ) -> bool:
        """Безопасно отправляет сообщение с клавиатурой.

        Args:
            chat_id: ID чата.
            text: Текст сообщения (HTML).
            markup: Клавиатура (InlineKeyboardMarkup).

        Returns:
            True если сообщение отправлено.
        """
        try:
            await self._bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)
            return True
        except Exception as exc:
            logger.error("Failed to send message with markup to chat_id=%s: %s", chat_id, exc)
            return False

    async def _safe_send(self, chat_id: int, text: str) -> bool:
        """Безопасно отправляет простое текстовое сообщение.

        FIXED архитектурное замечание: TelegramForbiddenError (бот заблокирован пользователем)
        логируется как WARNING — пользователь сам отозвал доступ, это не ошибка приложения.
        Остальные ошибки — ERROR. Можно расширить: при Forbidden удалять пользователя из рассылки.

        Args:
            chat_id: ID чата.
            text: Текст сообщения (HTML).

        Returns:
            True если сообщение отправлено.
        """
        try:
            await self._bot.send_message(chat_id, text, parse_mode="HTML")
            return True
        except Exception as exc:
            exc_name = type(exc).__name__
            # FIXED: TelegramForbiddenError — бот заблокирован пользователем, это ожидаемо
            if "Forbidden" in exc_name or "BotBlocked" in exc_name or "UserDeactivated" in exc_name:
                logger.warning(
                    "Cannot send message to chat_id=%s — bot blocked or user deactivated: %s",
                    chat_id, exc,
                )
            else:
                logger.error("Failed to send message to chat_id=%s: %s", chat_id, exc)
            return False
