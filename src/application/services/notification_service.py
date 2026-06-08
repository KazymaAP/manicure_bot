"""
src/application/services/notification_service.py — Сервис уведомлений.

✅ Из v2_tar: все методы уведомлений + _safe_send
✅ FIXED BUG-6: notify_admin_cancellation принимает appointment_id (int) — единая сигнатура.
   Все вызовы в коде используют ID, объект загружается внутри метода.
✅ FIXED BUG-05: _safe_send использует isinstance(TelegramForbiddenError) вместо хрупкой
   проверки по имени класса через строку. Пользователи с Forbidden-ошибкой помечаются
   как неактивные для исключения из будущих рассылок.
✅ FIXED BUG-4: is_bot_blocked сохраняется в БД (таблица users) через _appointment_repo.
   При Forbidden-ошибке флаг записывается в БД. При отправке проверяется БД.
"""
from __future__ import annotations

import asyncio
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
        address: str | None = None,
    ) -> None:
        """Инициализирует сервис уведомлений.

        Args:
            bot: Экземпляр Telegram бота.
            admin_ids: Telegram IDs администраторов.
            schedule_channel_id: ID канала для публикации расписания.
            appointment_repo: Репозиторий записей.
            service_name: Название услуги для уведомлений.
            address: Адрес студии (используется в напоминаниях).
        """
        self._bot = bot
        self._admin_ids = admin_ids
        self._schedule_channel_id = schedule_channel_id
        self._appointment_repo = appointment_repo
        self._service_name = service_name
        # FIXED M-06: _address теперь корректно устанавливается из параметра конструктора,
        # а не через getattr с пустым fallback. Адрес теперь отображается в напоминаниях.
        self._address: str = address or ""
        # FIXED BUG-05: множество user_id, заблокировавших бота — исключаем из рассылок.
        # FIXED BUG-4: кэш в памяти + персистентность в БД через _mark_blocked_in_db()
        self._blocked_users: set[int] = set()

    def _is_blocked_in_db(self, user_id: int) -> bool:
        """FIXED BUG-4: проверяет флаг is_bot_blocked в БД users.

        ПРОБЛЕМА 12 FIX: используем публичное свойство .db из BaseRepository
        вместо getattr(обхода инкапсуляции).
        """
        try:
            db = self._appointment_repo.db
            if db is None:
                return False
            with db.read_connection() as conn:
                row = conn.execute(
                    "SELECT is_bot_blocked FROM users WHERE user_id = ?", (user_id,)
                ).fetchone()
                if row is not None:
                    return bool(row[0])
        except Exception as exc:
            logger.debug("Cannot check is_bot_blocked for %s: %s", user_id, exc)
        return False

    def _mark_blocked_in_db(self, user_id: int) -> None:
        """FIXED BUG-4: записывает is_bot_blocked=1 в таблицу users.

        ПРОБЛЕМА 12 FIX: используем публичное свойство .db из BaseRepository.
        """
        try:
            db = self._appointment_repo.db
            if db is None:
                return
            with db.transaction() as conn:
                conn.execute(
                    "INSERT INTO users (user_id, is_bot_blocked) VALUES (?, 1) "
                    "ON CONFLICT(user_id) DO UPDATE SET is_bot_blocked = 1",
                    (user_id,)
                )
        except Exception as exc:
            logger.warning("Cannot mark user %s as blocked in DB: %s", user_id, exc)

    def load_blocked_from_db(self) -> None:
        """FIXED BUG-4: загружает список заблокировавших пользователей из БД в кэш памяти.

        Вызывать при старте бота для восстановления кэша после перезапуска.

        ПРОБЛЕМА 12 FIX: используем публичное свойство .db из BaseRepository.
        """
        try:
            db = self._appointment_repo.db
            if db is None:
                return
            with db.read_connection() as conn:
                rows = conn.execute(
                    "SELECT user_id FROM users WHERE is_bot_blocked = 1"
                ).fetchall()
                for row in rows:
                    self._blocked_users.add(row[0])
            logger.info("Loaded %d blocked users from DB", len(self._blocked_users))
        except Exception as exc:
            logger.warning("Cannot load blocked users from DB: %s", exc)

    async def notify_admin_new_booking(self, appointment_id: int) -> None:
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
        import asyncio

        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        # FIXED: используем карточное напоминание с деталями визита и кнопками
        appt = await asyncio.to_thread(self._appointment_repo.get_by_id, appointment_id)
        client_name = appt.client_name if appt else ""
        date = appt.date if appt else ""
        # FIXED M-06: используем self._address, корректно заданный в __init__
        address = self._address
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

        FIXED BUG-05: использует isinstance(exc, TelegramForbiddenError) вместо хрупкой
        проверки имени класса через строку. Имена классов aiogram могут меняться между
        версиями, isinstance() — надёжный способ проверки типа исключения.
        При Forbidden-ошибке user_id добавляется в _blocked_users и исключается из
        будущих рассылок, что предотвращает бесконечный рост нагрузки.

        FIXED H-7: обрабатывает TelegramRetryAfter (429 Too Many Requests) —
        ждёт указанное время и делает повторную попытку вместо тихой потери сообщения.

        Args:
            chat_id: ID чата.
            text: Текст сообщения (HTML).

        Returns:
            True если сообщение отправлено.
        """
        # FIXED BUG-05: проверяем, не заблокировал ли пользователь бота ранее
        # FIXED BUG-4: проверяем и кэш памяти, и БД (для персистентности)
        if chat_id in self._blocked_users:
            logger.debug("Skipping send to blocked user %s (memory cache)", chat_id)
            return False
        # Если в памяти нет — проверяем БД (на случай перезапуска)
        if self._is_blocked_in_db(chat_id):
            self._blocked_users.add(chat_id)  # добавляем в кэш
            logger.debug("Skipping send to blocked user %s (DB)", chat_id)
            return False

        max_retries = 3
        for attempt in range(max_retries):
            try:
                await self._bot.send_message(chat_id, text, parse_mode="HTML")
                return True
            except Exception as exc:
                # FIXED H-7: обработка flood control (429 Too Many Requests)
                try:
                    from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
                    if isinstance(exc, TelegramRetryAfter):
                        retry_after = getattr(exc, "retry_after", 5)
                        logger.warning(
                            "Rate limit hit for chat_id=%s, retry after %s seconds (attempt %d/%d)",
                            chat_id, retry_after, attempt + 1, max_retries,
                        )
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_after)
                            continue
                        else:
                            logger.error("Max retries exceeded for chat_id=%s after TelegramRetryAfter", chat_id)
                            return False
                    # FIXED BUG-05: используем isinstance() с реальным классом aiogram,
                    # а не хрупкую проверку по имени класса через строку.
                    if isinstance(exc, TelegramForbiddenError):
                        logger.warning(
                            "Cannot send message to chat_id=%s — bot blocked by user: %s. "
                            "Adding to blocked list to prevent future sends.",
                            chat_id, exc,
                        )
                        # FIXED BUG-05/BUG-4: помечаем как заблокированного — кэш + БД
                        self._blocked_users.add(chat_id)
                        self._mark_blocked_in_db(chat_id)  # FIXED BUG-4: персистентность
                        return False
                except ImportError:
                    # Fallback если структура aiogram.exceptions изменилась
                    exc_name = type(exc).__name__
                    if "RetryAfter" in exc_name or "TooManyRequests" in exc_name:
                        retry_after = getattr(exc, "retry_after", 5)
                        logger.warning("Rate limit (fallback): chat_id=%s, retry after %ss", chat_id, retry_after)
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_after)
                            continue
                        return False
                    if "Forbidden" in exc_name or "BotBlocked" in exc_name or "UserDeactivated" in exc_name:
                        logger.warning(
                            "Cannot send message to chat_id=%s — bot blocked or user deactivated: %s",
                            chat_id, exc,
                        )
                        self._blocked_users.add(chat_id)
                        self._mark_blocked_in_db(chat_id)  # FIXED BUG-4: персистентность
                        return False
                logger.error("Failed to send message to chat_id=%s: %s", chat_id, exc)
                return False
        return False
