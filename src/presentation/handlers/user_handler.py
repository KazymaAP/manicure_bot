# src/presentation/handlers/user_handler.py
"""FSM-обработчики для записи клиента на маникюр."""

import logging
from datetime import date as _date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from src.config.dependencies import Container
from src.domain.enums.fsm_states import BookingFSM
from aiogram.types import InlineKeyboardMarkup

from src.domain.exceptions.appointment import (
    MaxAppointmentsReachedError,
    SlotAlreadyBookedError,
)
from src.presentation.formatters.message_formatter import MessageFormatter
from src.presentation.handlers.common_handler import _get_portfolio
from src.presentation.keyboards.booking import BookingKeyboard
from src.presentation.keyboards.calendar import CalendarKeyboard
from src.presentation.keyboards.main_menu import MainMenuKeyboard

logger = logging.getLogger(__name__)

router = Router(name="user")


def setup_user_router(container: Container) -> Router:  # noqa: C901
    """Фабрика роутера — привязывает сервисы к хэндлерам."""

    appt_service = container.appointment_service
    sched_service = container.schedule_service
    notif_service = container.notification_service
    reminder_service = container.reminder_service
    settings = container.settings

    # ── «Записаться» ──────────────────────────────────────────────────────
    @router.message(F.text == "📅 Записаться")
    async def start_booking(message: Message, state: FSMContext) -> None:
        # FIXED H-01: сбрасываем предыдущие данные FSM перед началом нового потока записи.
        # Без этого прошлые данные (client_name, phone, transfer_source и т.д.)
        # остаются в state и вызывают некорректное поведение при повторном нажатии.
        await state.clear()

        # FIXED: проверяем подписку при ключевых действиях
        if settings.required_channel and message.from_user.id not in settings.admin_ids:
            try:
                member = await message.bot.get_chat_member(settings.required_channel, message.from_user.id)
                status = getattr(member, "status", None)
                if status in ("left", "kicked", "banned"):
                    await message.answer(
                        MessageFormatter.error_subscription_required(settings.required_channel),
                        reply_markup=MainMenuKeyboard.subscribe(settings.required_channel),
                        parse_mode="HTML",
                    )
                    return
            except Exception:
                # при ошибке проверки не блокируем пользователя (как и в common handler)
                pass

        # Предлагаем выбрать услугу перед датой
        # FIXED: передаём settings.services для динамической генерации кнопок
        await state.set_state(BookingFSM.choosing_service)
        await message.answer(MessageFormatter._tpl("booking.choose_service", "Выберите услугу:"), reply_markup=BookingKeyboard.service_selection(settings.services or None))

        # FIXED: добавляем кнопку "Использовать прошлые данные" если у пользователя есть прошлые записи
        import asyncio
        prev = await asyncio.to_thread(appt_service.get_user_appointments, message.from_user.id)
        if prev:
            await message.answer("Хотите использовать прошлые данные?", reply_markup=BookingKeyboard.use_previous_data())


    # ── Выбор услуги ───────────────────────────────────────────────────────
    @router.callback_query(BookingFSM.choosing_service, F.data.startswith("service:"))
    async def choose_service(callback: CallbackQuery, state: FSMContext) -> None:
        _, svc = callback.data.split(":", 1)
        # сохраняем выбранную услугу и показываем календарь
        await state.update_data(service=svc)
        available_dates = await sched_service.get_available_dates_async()
        if not available_dates:
            await callback.message.answer(MessageFormatter.no_available_dates())
            await state.clear()
            return
        today = _date.today()
        cal = CalendarKeyboard.build(
            year=today.year,
            month=today.month,
            available_dates=set(available_dates),
        )
        await state.set_state(BookingFSM.choosing_date)
        await callback.message.edit_text(MessageFormatter.choose_date(), reply_markup=cal)
        await callback.answer()

    @router.callback_query(F.data == "use_prev")
    async def use_previous_data(callback: CallbackQuery, state: FSMContext) -> None:
        """Автозаполнение имени и телефона из последней записи пользователя."""
        import asyncio
        appts = await asyncio.to_thread(appt_service.get_user_appointments, callback.from_user.id)
        if not appts:
            await callback.answer("Прошлых записей не найдено.", show_alert=True)
            return
        last = appts[-1]
        await state.update_data(client_name=last.client_name, phone=last.phone)
        await callback.answer("Данные заполнены из последней записи.")
        # Предложим выбрать услугу (если не выбрана)
        if not (await state.get_data()).get("service"):
            await callback.message.answer(MessageFormatter._tpl("booking.choose_service", "Выберите услугу:"), reply_markup=BookingKeyboard.service_selection(settings.services or None))
        else:
            await callback.message.answer("Данные заполнены. Выберите дату и время.")

    # УДАЛЕНО: дублирующий хендлер transfer_appt
    # Используется transfer_appointment_start из extended_features_handler.py с callback_data="transfer_appt:"

    # ── Навигация по календарю ────────────────────────────────────────────
    @router.callback_query(BookingFSM.choosing_date, F.data.startswith("cal_prev:") | F.data.startswith("cal_next:"))
    async def calendar_navigate(callback: CallbackQuery, state: FSMContext) -> None:
        """Навигация по месяцам с корректным переходом года."""
        parts = callback.data.split(":")
        direction = parts[0]  # "cal_prev" или "cal_next"
        year, month = int(parts[1]), int(parts[2])

        # Переходим к предыдущему или следующему месяцу
        if direction == "cal_prev":
            month -= 1
            if month < 1:
                month = 12
                year -= 1
        else:  # cal_next
            month += 1
            if month > 12:
                month = 1
                year += 1

        # Не позволяем уйти в прошлое
        today = _date.today()
        if year < today.year or (year == today.year and month < today.month):
            await callback.answer()
            return

        available_dates = await sched_service.get_available_dates_async()
        cal = CalendarKeyboard.build(
            year=year,
            month=month,
            available_dates=set(available_dates),
        )
        await callback.message.edit_reply_markup(reply_markup=cal)
        await callback.answer()

    # ── Выбор даты ────────────────────────────────────────────────────────
    @router.callback_query((BookingFSM.choosing_date | BookingFSM.choosing_service), F.data.startswith("cal_day:"))
    async def choose_date(callback: CallbackQuery, state: FSMContext) -> None:
        _, date_str = callback.data.split(":", 1)
        slots = await sched_service.get_available_slots(date_str)
        if not slots:
            # Предложим пользователю встать в лист ожидания
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔔 Уведомить о свободном месте", callback_data=f"join_waitlist:{date_str}")]])
            await callback.answer(MessageFormatter.no_available_slots(), show_alert=True)
            await callback.message.answer(MessageFormatter.no_available_slots(), reply_markup=kb)
            return

        await state.update_data(chosen_date=date_str)
        await state.set_state(BookingFSM.choosing_time)
        await callback.message.edit_text(
            MessageFormatter.choose_time(),
            reply_markup=BookingKeyboard.time_slots(date_str, slots),
        )
        await callback.answer()

    # ── Ignore non-available calendar taps ───────────────────────────────
    @router.callback_query(BookingFSM.choosing_date, F.data == "calendar_ignore")
    async def calendar_empty(callback: CallbackQuery) -> None:
        await callback.answer()

    # ── Выбор времени ─────────────────────────────────────────────────────
    @router.callback_query(BookingFSM.choosing_time, F.data.startswith("slot:"))
    async def choose_time(callback: CallbackQuery, state: FSMContext) -> None:
        parts = callback.data.split(":", 2)
        time_str = parts[2].replace("-", ":")
        await state.update_data(chosen_time=time_str)
        # Если в state есть transfer_source — это перенос записи, оставляем имя/phone из state и сразу просим подтверждение
        data = await state.get_data()
        if data.get("client_name") and data.get("phone"):
            await state.set_state(BookingFSM.entering_comment)
            await callback.message.edit_text(MessageFormatter.enter_comment(), reply_markup=BookingKeyboard.skip_comment())
        else:
            await state.set_state(BookingFSM.entering_name)
            await callback.message.edit_text(MessageFormatter.enter_name(), reply_markup=None)
        await callback.answer()

    # ── Напоминания: кнопки from client
    @router.callback_query(F.data.startswith("reminder_yes:"))
    async def reminder_yes(callback: CallbackQuery) -> None:
        appt_id = int(callback.data.split(":")[1])
        # Подтверждение прихода — спасибо
        await callback.answer("Спасибо! Ждём вас на приёме.")
        try:
            # Опционально — пометим reminder_sent (если ещё не помечено)
            import asyncio
            await asyncio.to_thread(appt_service.mark_reminder_sent, appt_id)
        except Exception:
            logger.exception("Failed to mark reminder as sent for %s", appt_id)

    @router.callback_query(F.data.startswith("reminder_no:"))
    async def reminder_no(callback: CallbackQuery) -> None:
        appt_id = int(callback.data.split(":")[1])
        import asyncio
        try:
            appt = await asyncio.to_thread(appt_service.get_appointment_by_id, appt_id)
            if not appt or appt.user_id != callback.from_user.id:
                await callback.answer(MessageFormatter.appointment_not_found(), show_alert=True)
                return
            await asyncio.to_thread(appt_service.cancel_by_id, appt_id)
            await notif_service.notify_admin_cancellation(appt_id)
            await callback.answer("Ваша запись отменена.")
        except Exception:
            logger.exception("Failed to cancel appointment via reminder: %s", appt_id)
            await callback.answer(MessageFormatter.error_general(), show_alert=True)

    # ── Ввод имени ────────────────────────────────────────────────────────
    @router.message(BookingFSM.entering_name, F.text)
    async def enter_name(message: Message, state: FSMContext) -> None:
        name = message.text.strip()
        if len(name) < 2 or len(name) > 100:
            await message.answer(MessageFormatter.invalid_name())
            return
        await state.update_data(client_name=name)
        await state.set_state(BookingFSM.entering_phone)
        await message.answer(MessageFormatter.enter_phone(), parse_mode="HTML")

    # ── Ввод телефона ─────────────────────────────────────────────────────
    @router.message(BookingFSM.entering_phone, F.text)
    async def enter_phone(message: Message, state: FSMContext) -> None:
        phone = message.text.strip()
        # FIXED: Укреплённая валидация телефона — минимум 7 цифр, E.164-подобный формат и не все цифры одинаковые
        digits = "".join(c for c in phone if c.isdigit())
        import re
        if len(digits) < 7 or len(digits) > 15:
            await message.answer(MessageFormatter.invalid_phone())
            return
        if len(set(digits)) == 1:
            await message.answer(MessageFormatter.invalid_phone())
            return
        # Разрешаем формат с опциональным '+' и цифрами (приблизительно E.164)
        normalized = re.sub(r"[\s\-()]+", "", phone)
        if not re.match(r"^\+?[0-9]{7,15}$", normalized):
            await message.answer(MessageFormatter.invalid_phone())
            return
        await state.update_data(phone=phone)
        await state.set_state(BookingFSM.entering_comment)
        await message.answer(
            MessageFormatter.enter_comment(),
            reply_markup=BookingKeyboard.skip_comment(),
            parse_mode="HTML",
        )

    # ── Ввод комментария ──────────────────────────────────────────────────
    @router.message(BookingFSM.entering_comment, F.text)
    async def enter_comment(message: Message, state: FSMContext) -> None:
        skip_texts = {"пропустить", "skip", "➡️ пропустить"}
        comment = None if message.text.strip().lower() in skip_texts else message.text.strip()
        await state.update_data(comment=comment)
        await _show_confirmation(message, state)

    @router.callback_query(BookingFSM.entering_comment, F.data == "skip_comment")
    async def skip_comment(callback: CallbackQuery, state: FSMContext) -> None:
        await state.update_data(comment=None)
        await callback.answer()
        await _show_confirmation(callback.message, state)

    async def _show_confirmation(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        # FIXED: показываем карточку записи с рамкой и призывом к действию
        card = MessageFormatter.appointment_card_box(
            date_str=data["chosen_date"],
            time_str=data["chosen_time"],
            client_name=data["client_name"],
            phone=data["phone"],
            comment=data.get("comment"),
            service=data.get("service"),
        )
        await state.set_state(BookingFSM.confirming)
        await message.answer(
            card,
            reply_markup=BookingKeyboard.confirm(),
            parse_mode="HTML",
        )

    # ── Подтверждение / отмена бронирования ──────────────────────────────
    @router.callback_query(BookingFSM.confirming, F.data == "booking_confirm")
    async def confirm_booking(callback: CallbackQuery, state: FSMContext) -> None:
        # Сразу подтверждаем callback чтобы убрать "часики" в Telegram
        await callback.answer()
        data = await state.get_data()
        user_id = callback.from_user.id
        import asyncio
        try:
            # Выполняем блокирующую операцию в фоновом потоке, чтобы не блокировать event loop
            appointment_id = await asyncio.to_thread(
                appt_service.create_appointment,
                user_id,
                data["chosen_date"],
                data["chosen_time"],
                data["client_name"],
                data["phone"],
                data.get("comment"),
                callback.from_user.username,  # FIXED: передаём username
                data.get("service"),
            )
            # Если это перенос (есть transfer_source) — после создания новой записи отменим старую
            if data.get("transfer_source"):
                try:
                    await asyncio.to_thread(appt_service.cancel_by_id, data.get("transfer_source"))
                except Exception:
                    logger.exception("Не удалось отменить старую запись при переносе %s", data.get("transfer_source"))
            # Уведомить администратора о новой записи
            await notif_service.notify_admin_new_booking(appointment_id)
            # Запланировать напоминание клиенту (scheduler — async-safe)
            # FIXED C-06: передаём timezone из settings для корректного расчёта времени
            reminder_service.schedule_reminder(
                appointment_id=appointment_id,
                user_id=user_id,
                date_str=data["chosen_date"],
                time_str=data["chosen_time"],
                timezone_str=settings.timezone,
            )
            is_admin = user_id in settings.admin_ids
            portfolio = _get_portfolio(settings)
            await callback.message.edit_text(
                MessageFormatter.booking_success(
                    data["chosen_date"],
                    data["chosen_time"],
                    hours_before=settings.reminder_hours_before,
                ),
                parse_mode="HTML",
            )
            # FIXED: если пользователь использовал transfer — удалим transfer_source из state
            try:
                if data.get("transfer_source"):
                    await state.update_data(transfer_source=None)
            except Exception:
                pass
            await callback.message.answer(
                MessageFormatter.main_menu_title(),
                reply_markup=MainMenuKeyboard.main(is_admin=is_admin, portfolio_url=portfolio),
            )
        except SlotAlreadyBookedError:
            await callback.message.answer(MessageFormatter.slot_already_taken())
        except Exception as exc:
            # Разворачиваем специфичные ошибки
            from src.domain.exceptions.appointment import MaxAppointmentsReachedError, BlacklistedUserError
            if isinstance(exc, BlacklistedUserError):
                await callback.message.answer(MessageFormatter.user_blocked())
            elif isinstance(exc, MaxAppointmentsReachedError):
                await callback.message.answer(MessageFormatter.max_appointments_reached(exc.max_count))
            else:
                logger.error("Ошибка создания записи для %s: %s", user_id, exc)
                await callback.message.answer(MessageFormatter.error_general())
        finally:
            # FIXED: гарантированно очищаем FSM-состояние, чтобы пользователь не застрял
            try:
                await state.clear()
            except Exception:
                logger.exception("Не удалось очистить состояние FSM при confirm_booking")

    @router.callback_query(BookingFSM.confirming, F.data == "booking_cancel")
    async def cancel_booking(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        is_admin = callback.from_user.id in settings.admin_ids
        portfolio = _get_portfolio(settings)
        await callback.message.edit_text(MessageFormatter.booking_cancelled_by_user())
        await callback.message.answer(
            MessageFormatter.main_menu_title(),
            reply_markup=MainMenuKeyboard.main(is_admin=is_admin, portfolio_url=portfolio),
        )
        await callback.answer()

    # ── Мои записи ────────────────────────────────────────────────────────
    @router.message(F.text == "📋 Мои записи")
    async def my_appointments(message: Message) -> None:
        import asyncio
        # FIXED: проверка подписки
        if settings.required_channel and message.from_user.id not in settings.admin_ids:
            try:
                member = await message.bot.get_chat_member(settings.required_channel, message.from_user.id)
                status = getattr(member, "status", None)
                if status in ("left", "kicked", "banned"):
                    await message.answer(
                        MessageFormatter.error_subscription_required(settings.required_channel),
                        reply_markup=MainMenuKeyboard.subscribe(settings.required_channel),
                        parse_mode="HTML",
                    )
                    return
            except Exception:
                pass

        user_id = message.from_user.id
        # FIXED: вызываем синхронную DB-операцию в background thread
        appointments = await asyncio.to_thread(appt_service.get_user_appointments, user_id)
        if not appointments:
            await message.answer(MessageFormatter.my_appointments_empty())
            return
        text = MessageFormatter.my_appointments_list_blocks(appointments)
        await message.answer(
            text,
            reply_markup=BookingKeyboard.cancel_appointment_list(appointments),
            parse_mode="HTML",
        )
        # FIXED: добавляем кнопку переноса к каждому элементу списка — пользователь сможет выбрать новую дату/время
        # Реализовано через callback transfer_appt:<id>

    # ── Ближайшие слоты (только кнопка, Command в final_features_handler.py)
    @router.message(F.text == "🟢 Ближайшие слоты")
    async def nearest_slots(message: Message) -> None:
        slots = await sched_service.get_nearest_slots_async(limit=5)
        if not slots:
            await message.answer(MessageFormatter.no_available_dates())
            return
        lines = ["📅 <b>Ближайшие свободные слоты:</b>\n"]
        from src.presentation.constants import MONTHS_RU_GEN
        for date_str, time_str in slots:
            d = __import__("datetime").datetime.strptime(date_str, "%Y-%m-%d")
            formatted_date = f"{d.day} {MONTHS_RU_GEN[d.month]} {d.year}"
            lines.append(f"• {formatted_date} в {time_str}")
        await message.answer("\n".join(lines), parse_mode="HTML")

    @router.callback_query(F.data.startswith("cancel_appt:"))
    async def cancel_appointment(callback: CallbackQuery) -> None:
        import asyncio
        appt_id = int(callback.data.split(":")[1])
        answered = False
        try:
            # FIXED: выполняем отмену в фоновом потоке
            await asyncio.to_thread(appt_service.cancel_appointment, appt_id, callback.from_user.id)
            # Уведомляем администратора об отмене
            await notif_service.notify_admin_cancellation(appt_id)
            await callback.message.edit_text(
                MessageFormatter.appointment_cancel_success(),
                reply_markup=None,
            )
            await callback.answer()
            answered = True
        except Exception as exc:
            logger.warning("Не удалось отменить запись %s: %s", appt_id, exc)
            await callback.answer(MessageFormatter.appointment_not_found(), show_alert=True)
            answered = True
        finally:
            if not answered:
                await callback.answer()

    # УДАЛЕНО: дублирующий хендлер join_waitlist
    # Используется join_waitlist из extended_features_handler.py с callback_data="join_waitlist:"

    # ── Возврат к выбору даты из выбора времени (H-09) ───────────────────
    @router.callback_query(BookingFSM.choosing_time, F.data == "book_start")
    async def back_to_booking(callback: CallbackQuery, state: FSMContext) -> None:
        """Возвращает пользователя к выбору даты при нажатии 'Назад'."""
        available_dates = await sched_service.get_available_dates_async()
        if not available_dates:
            await callback.answer(MessageFormatter.no_available_dates(), show_alert=True)
            await state.clear()
            return
        today = _date.today()
        cal = CalendarKeyboard.build(
            year=today.year,
            month=today.month,
            available_dates=set(available_dates),
        )
        await state.set_state(BookingFSM.choosing_date)
        await callback.message.edit_text(
            MessageFormatter.choose_date(),
            reply_markup=cal,
        )
        await callback.answer()

    # ── Главное меню из списка записей (H-07) ────────────────────────────
    @router.callback_query(F.data == "main_menu")
    async def main_menu(callback: CallbackQuery, state: FSMContext) -> None:
        """Возвращает пользователя в главное меню."""
        await state.clear()
        is_admin = callback.from_user.id in settings.admin_ids
        portfolio = _get_portfolio(settings)
        await callback.message.edit_text(
            MessageFormatter.main_menu_title(),
            reply_markup=MainMenuKeyboard.main(is_admin=is_admin, portfolio_url=portfolio),
            parse_mode="HTML",
        )
        await callback.answer()

    return router
