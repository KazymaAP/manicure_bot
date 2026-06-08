"""
src/presentation/handlers/final_features_handler.py — Финальные фичи.

FIXED BUG-7,8,9: удалены дублирующие archive_old_appointments(), check_insufficient_slots(),
register_scheduled_jobs(). Единственные реализации — в reminder_service.py.

FIXED BUG-12: dynamic SQL заменён на фиксированные запросы.
"""

import asyncio
import logging
from datetime import date as _date

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
)

from src.config.dependencies import Container
from src.presentation.formatters.message_formatter import MessageFormatter
from src.presentation.keyboards.main_menu import MainMenuKeyboard
from src.presentation.keyboards.notifications import NotificationKeyboard

logger = logging.getLogger(__name__)
router = Router(name="final_features")


def setup_final_features_router(container: Container) -> Router:
    """Фабрика роутера финальных функций."""

    appt_service = container.appointment_service
    sched_service = container.schedule_service
    # FIXED БАГ-КРИТ-05: получаем db (DatabaseManager) из container вместо сырого sqlite3.connect()
    db = container.db
    # ПРОБЛЕМА 8 FIX: используем метод сервиса вместо дублирующей локальной функции
    # _get_user_notif_settings удалена — используем appt_service.get_user_notification_settings()

    # ═══════════════════════════════════════════════════════════════════════
    # КОМАНДЫ И КНОПКИ
    # ═══════════════════════════════════════════════════════════════════════

    # ── #8 /mybookings — быстрый доступ к записям ──────────────────────────
    @router.message(Command("mybookings"))
    async def cmd_my_bookings(message: Message) -> None:
        """FIXED: фича #8 — команда для быстрого доступа к записям."""

        user_id = message.from_user.id
        appts = await asyncio.to_thread(appt_service.get_user_appointments, user_id)

        if not appts:
            await message.answer(
                "📭 У вас пока нет активных записей.\n\n"
                "Нажмите кнопку '📅 Записаться' для создания новой записи.",
                reply_markup=MainMenuKeyboard.main(),
            )
            return

        text = "📋 <b>Ваши записи:</b>\n\n"
        for appt in appts:
            text += (
                f"📅 <b>{appt.date}</b> в <b>{appt.time}</b>\n"
                f"   Услуга: {appt.service or 'маникюр'}\n"
                f"   Комментарий: {appt.comment or 'нет'}\n\n"
            )

        from src.presentation.keyboards.booking import BookingKeyboard

        # FIXED BUG 3: метод my_appointments_actions не существует, используем cancel_appointment_list
        kb = BookingKeyboard.cancel_appointment_list(appts)
        await message.answer(text, reply_markup=kb)

    # ── #5 /slots — ближайшие свободные слоты ──────────────────────────────
    @router.message(Command("slots"))
    async def cmd_nearest_slots(message: Message) -> None:
        """FIXED: фича #5 — ближайшие 5 свободных слотов."""
        try:
            available_dates = await sched_service.get_available_dates_async()
            if not available_dates:
                await message.answer("❌ " + MessageFormatter.no_available_dates())
                return

            slots = []
            for date_str in available_dates[:5]:
                # FIXED BUG 2: используем get_available_slots вместо get_available_times
                slot_objs = await sched_service.get_available_slots(date_str)
                times = [s.time for s in slot_objs]
                if times:
                    slots.append((date_str, times[0]))

            if not slots:
                await message.answer("❌ Нет доступных слотов")
                return

            text = MessageFormatter.nearby_slots_list(slots)
            from src.presentation.keyboards.calendar import CalendarKeyboard

            kb = CalendarKeyboard.build(
                year=_date.today().year,
                month=_date.today().month,
                available_dates=set(available_dates),
            )
            await message.answer(text, reply_markup=kb)
        except Exception as exc:
            logger.exception("Error in /slots: %s", exc)
            await message.answer("❌ Ошибка при загрузке слотов")

    # ── #46 /schedule — расписание для клиентов ────────────────────────────
    @router.message(F.text == "📆 Расписание")
    async def view_schedule_for_client(message: Message) -> None:
        """FIXED: фича #46 — просмотр расписания с количеством свободных мест."""
        try:
            available_dates = await sched_service.get_available_dates_async()
            if not available_dates:
                await message.answer("❌ Расписание пока не открыто")
                return

            # Получаем количество слотов на каждую дату
            # FIXED BUG 2: используем get_available_slots вместо get_available_times
            free_slots = {}
            for date_str in available_dates[:10]:
                slot_objs = await sched_service.get_available_slots(date_str)
                free_slots[date_str] = len(slot_objs)

            text = MessageFormatter.schedule_view_for_client(available_dates[:10], free_slots)
            await message.answer(text)
        except Exception as exc:
            logger.exception("Schedule view error: %s", exc)
            await message.answer("❌ Ошибка при загрузке расписания")

    # ── #20 Контакты — перенесены в common_handler ─────────────────────────
    # Обработчик «📞 Связаться с мастером» и «📞 Контакты» находится в common_handler.py

    # ── #21 Цены — перенесены в common_handler ─────────────────────────────
    # Обработчик «💰 Цены» находится в common_handler.py

    # ── #19 /share — поделиться ботом ────────────────────────────────────
    @router.message(F.text == "📤 Поделиться")
    async def share_bot(message: Message) -> None:
        """FIXED: фича #19 — готовая ссылка для реферального распространения."""
        bot_info = await message.bot.get_me()
        bot_username = bot_info.username if bot_info else None
        if bot_username:
            text = MessageFormatter.share_bot_link(bot_username)
            await message.answer(text)
        else:
            # Пункт 19: понятное сообщение вместо error_general
            await message.answer("❌ Не удалось получить ссылку на бота. Попробуйте позже.")

    # ── #49 Управление уведомлениями ─────────────────────────────────────
    @router.message(F.text == "🔔 Уведомления")
    async def manage_notifications(message: Message) -> None:
        """FIXED BUG-09: фича #49 — управление уведомлениями и напоминаниями."""

        user_id = message.from_user.id
        # ПРОБЛЕМА 8 FIX: используем appt_service.get_user_notification_settings вместо
        # дублирующей локальной функции _get_user_notif_settings
        notif_settings = await asyncio.to_thread(appt_service.get_user_notification_settings, user_id)
        all_on = notif_settings.get("notifications_enabled", 1)
        # ПРОБЛЕМА 2/9 FIX: используем NotificationKeyboard.settings из keyboards/
        kb = NotificationKeyboard.settings(notif_settings)
        status_text = "включены ✅" if all_on else "отключены ❌"
        await message.answer(
            f"🔔 <b>Управление уведомлениями</b>\n\n"
            f"Текущий статус: <b>{status_text}</b>\n\n"
            "Выберите, когда получать напоминания о предстоящих записях:",
            reply_markup=kb,
        )

    def _update_user_notif(user_id: int, **kwargs) -> None:
        """Обновляет настройки уведомлений пользователя в БД.

        FIXED БАГ-КРИТ-05: используем db.transaction() из замыкания.
        FIXED BUG-12: заменены динамические запросы с именем колонки из переменной
        на отдельные фиксированные запросы для каждой колонки.
        """
        # FIXED BUG-12: допустимые колонки — фиксированный белый список
        _allowed_cols = {
            "notifications_enabled",
            "notif_24h",
            "notif_2h",
            "notif_1h",
        }
        try:
            with db.transaction() as conn:
                for col, val in kwargs.items():
                    if col not in _allowed_cols:
                        logger.warning("_update_user_notif: unknown column %r, skipping", col)
                        continue
                    # FIXED BUG-12: используем фиксированные запросы вместо f-string с именем колонки
                    if col == "notifications_enabled":
                        conn.execute(
                            "INSERT INTO users (user_id, notifications_enabled) VALUES (?, ?) "
                            "ON CONFLICT(user_id) DO UPDATE SET notifications_enabled = excluded.notifications_enabled",
                            (user_id, val)
                        )
                    elif col == "notif_24h":
                        conn.execute(
                            "INSERT INTO users (user_id, notif_24h) VALUES (?, ?) "
                            "ON CONFLICT(user_id) DO UPDATE SET notif_24h = excluded.notif_24h",
                            (user_id, val)
                        )
                    elif col == "notif_2h":
                        conn.execute(
                            "INSERT INTO users (user_id, notif_2h) VALUES (?, ?) "
                            "ON CONFLICT(user_id) DO UPDATE SET notif_2h = excluded.notif_2h",
                            (user_id, val)
                        )
                    elif col == "notif_1h":
                        conn.execute(
                            "INSERT INTO users (user_id, notif_1h) VALUES (?, ?) "
                            "ON CONFLICT(user_id) DO UPDATE SET notif_1h = excluded.notif_1h",
                            (user_id, val)
                        )
        except Exception as exc:
            logger.error("Failed to update notification settings for user %s: %s", user_id, exc)

    # ПРОБЛЕМА 2/9 FIX: _build_notif_keyboard удалена — используем NotificationKeyboard.settings()
    # из src/presentation/keyboards/notifications.py

    # FIXED BUG-09: хендлеры для всех 5 callback уведомлений (ранее отсутствовали)
    @router.callback_query(F.data == "notif_all_on")
    async def notif_all_on_handler(callback: CallbackQuery) -> None:
        """Включает все уведомления."""
        user_id = callback.from_user.id
        await asyncio.to_thread(_update_user_notif, user_id,
                                notifications_enabled=1, notif_24h=1, notif_2h=1, notif_1h=1)
        await callback.answer("✅ Все уведомления включены", show_alert=True)
        updated = {"notifications_enabled": 1, "notif_24h": 1, "notif_2h": 1, "notif_1h": 1}
        await callback.message.edit_text(
            "🔔 <b>Управление уведомлениями</b>\n\n"
            "Текущий статус: <b>включены ✅</b>\n\n"
            "Все напоминания активированы. Вы будете получать уведомления за 24ч, 2ч и 1ч до записи.",
            reply_markup=NotificationKeyboard.settings(updated),
            parse_mode="HTML",
        )

    @router.callback_query(F.data == "notif_all_off")
    async def notif_all_off_handler(callback: CallbackQuery) -> None:
        """Отключает все уведомления."""
        user_id = callback.from_user.id
        await asyncio.to_thread(_update_user_notif, user_id,
                                notifications_enabled=0, notif_24h=0, notif_2h=0, notif_1h=0)
        await callback.answer("❌ Все уведомления отключены", show_alert=True)
        updated = {"notifications_enabled": 0, "notif_24h": 0, "notif_2h": 0, "notif_1h": 0}
        await callback.message.edit_text(
            "🔔 <b>Управление уведомлениями</b>\n\n"
            "Текущий статус: <b>отключены ❌</b>\n\n"
            "Напоминания отключены. Нажмите '✅ Включить все' чтобы активировать снова.",
            reply_markup=NotificationKeyboard.settings(updated),
            parse_mode="HTML",
        )

    @router.callback_query(F.data == "notif_24h")
    async def notif_24h_handler(callback: CallbackQuery) -> None:
        """Переключает уведомление за 24 часа. FIXED БАГ #17: обновляет клавиатуру."""
        user_id = callback.from_user.id
        # ПРОБЛЕМА 8 FIX: используем appt_service.get_user_notification_settings
        current = await asyncio.to_thread(appt_service.get_user_notification_settings, user_id)
        new_val = 0 if current.get("notif_24h", 1) else 1
        await asyncio.to_thread(_update_user_notif, user_id, notif_24h=new_val)
        status = "включено 🔔" if new_val else "отключено 🔕"
        await callback.answer(f"Напоминание за 24 часа: {status}", show_alert=True)
        updated = {**current, "notif_24h": new_val}
        await callback.message.edit_reply_markup(reply_markup=NotificationKeyboard.settings(updated))

    @router.callback_query(F.data == "notif_2h")
    async def notif_2h_handler(callback: CallbackQuery) -> None:
        """Переключает уведомление за 2 часа. FIXED БАГ #17: обновляет клавиатуру."""
        user_id = callback.from_user.id
        # ПРОБЛЕМА 8 FIX: используем appt_service.get_user_notification_settings
        current = await asyncio.to_thread(appt_service.get_user_notification_settings, user_id)
        new_val = 0 if current.get("notif_2h", 1) else 1
        await asyncio.to_thread(_update_user_notif, user_id, notif_2h=new_val)
        status = "включено 🔔" if new_val else "отключено 🔕"
        await callback.answer(f"Напоминание за 2 часа: {status}", show_alert=True)
        updated = {**current, "notif_2h": new_val}
        await callback.message.edit_reply_markup(reply_markup=NotificationKeyboard.settings(updated))

    @router.callback_query(F.data == "notif_1h")
    async def notif_1h_handler(callback: CallbackQuery) -> None:
        """Переключает уведомление за 1 час. FIXED БАГ #17: обновляет клавиатуру."""
        user_id = callback.from_user.id
        # ПРОБЛЕМА 8 FIX: используем appt_service.get_user_notification_settings
        current = await asyncio.to_thread(appt_service.get_user_notification_settings, user_id)
        new_val = 0 if current.get("notif_1h", 1) else 1
        await asyncio.to_thread(_update_user_notif, user_id, notif_1h=new_val)
        status = "включено 🔔" if new_val else "отключено 🔕"
        await callback.answer(f"Напоминание за 1 час: {status}", show_alert=True)
        updated = {**current, "notif_1h": new_val}
        await callback.message.edit_reply_markup(reply_markup=NotificationKeyboard.settings(updated))

    # ═══════════════════════════════════════════════════════════════════════
    # АРХИВИРОВАНИЕ И ЧИСТКА
    # ═══════════════════════════════════════════════════════════════════════
    # FIXED BUG-7, BUG-8, BUG-9: дублирующие функции archive_old_appointments()
    # и check_insufficient_slots() удалены. Единственные реализации находятся
    # в reminder_service.py (_weekly_archive_job и _insufficient_slots_check_job).
    # Планировщик в main.py использует только reminder_service методы.
    # register_scheduled_jobs() также удалена как мёртвый код.

    # ═══════════════════════════════════════════════════════════════════════
    # INLINE РЕЖИМ (@bot дата в чате)
    # ═══════════════════════════════════════════════════════════════════════

    # ── #36 Inline режим поиска дат ────────────────────────────────────────
    @router.inline_query()
    async def inline_search_dates(inline_query: InlineQuery) -> None:
        """FIXED: фича #36 — inline режим для поиска дат.

        Использование: @bot_username дата слот1 слот2...
        """
        query = inline_query.query.strip().lower()
        if not query or len(query) < 4:
            await inline_query.answer([])
            return

        try:
            available_dates = await sched_service.get_available_dates_async()

            # Фильтруем даты по запросу
            matching_dates = [d for d in available_dates if query in d]

            if not matching_dates:
                await inline_query.answer([])
                return

            results = []
            for date_str in matching_dates[:5]:
                # FIXED C-02: метода get_available_times не существует, используем get_available_slots
                slot_objs = await sched_service.get_available_slots(date_str)
                times = [s.time for s in slot_objs]
                slots_text = ", ".join(times[:3]) if times else "нет слотов"

                result = InlineQueryResultArticle(
                    id=date_str,
                    title=f"📅 {date_str}",
                    description=f"Доступно: {slots_text}",
                    input_message_content=InputTextMessageContent(
                        message_text=(
                            f"<b>Дата:</b> {date_str}\n"
                            f"<b>Доступные слоты:</b>\n" + "\n".join([f"🕐 {t}" for t in (times or [])])
                        ),
                        parse_mode="HTML",
                    ),
                )
                results.append(result)

            await inline_query.answer(results)
        except Exception as exc:
            logger.exception("Inline search error: %s", exc)
            await inline_query.answer([])

    # FIXED BUG-9: register_scheduled_jobs() удалена — задачи уже зарегистрированы в
    # reminder_service.py. Атрибут router.register_scheduled_jobs также удалён.

    return router
