"""
src/presentation/handlers/user_handler.py — FSM-обработчики для записи клиента.

Обновлено: тёплый стиль, процесс записи «услуга → дата → время → подтверждение»,
напоминание с кнопками «Буду!» / «Отменить», благодарность после визита.
"""

import asyncio
import logging
import re
from datetime import date as _date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.config.dependencies import Container
from src.domain.enums.fsm_states import BookingFSM
from src.domain.exceptions.appointment import (
    AppointmentAlreadyCancelledError as _ApptAlreadyCancelledError,
)
from src.domain.exceptions.appointment import (
    AppointmentNotFoundError as _ApptNotFoundError,
)
from src.domain.exceptions.appointment import (
    SlotAlreadyBookedError,
)
from src.presentation.formatters.message_formatter import MessageFormatter
from src.presentation.handlers.common_handler import _get_portfolio, check_subscription
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
    @router.message(F.text.in_({"💅 Записаться", "📅 Записаться"}))
    async def start_booking(message: Message, state: FSMContext) -> None:
        """Начинает процесс записи — показывает список услуг."""
        await state.clear()

        # BUG 2.1 FIX: используем общую функцию check_subscription из common_handler
        # вместо дублирующей inline-логики
        is_subscribed = await check_subscription(message.from_user.id, message.bot, settings)
        if not is_subscribed:
            # БАГ 2 FIX: required_channel может быть None — добавляем guard
            if not settings.required_channel:
                await message.answer("❌ Подписка на канал не настроена")
                return
            await message.answer(
                MessageFormatter.error_subscription_required(settings.required_channel),
                reply_markup=MainMenuKeyboard.subscribe(settings.required_channel),
                parse_mode="HTML",
            )
            return

        # Показываем выбор услуг
        await state.set_state(BookingFSM.choosing_service)
        await message.answer(
            MessageFormatter.choose_service(),
            reply_markup=BookingKeyboard.service_selection(settings.services or None),
            parse_mode="HTML",
        )

        # Предлагаем использовать прошлые данные если они есть
        try:
            prev = await asyncio.to_thread(appt_service.get_user_appointments, message.from_user.id)
            if prev:
                await message.answer(
                    "🔄 Хочешь использовать данные из предыдущей записи?",
                    reply_markup=BookingKeyboard.use_previous_data(),
                )
        except Exception:
            pass

    # ── Выбор услуги ───────────────────────────────────────────────────────
    @router.callback_query(BookingFSM.choosing_service, F.data.startswith("service:"))
    async def choose_service(callback: CallbackQuery, state: FSMContext) -> None:
        """Сохраняет выбранную услугу и показывает календарь."""
        _, svc = callback.data.split(":", 1)
        await state.update_data(service=svc)

        available_dates = await sched_service.get_available_dates_async()
        # БАГ 1 FIX: проверка типа msg
        msg = callback.message
        if not isinstance(msg, Message):
            await callback.answer()
            return
        if not available_dates:
            await msg.answer(
                MessageFormatter.no_available_dates(),
                parse_mode="HTML",
            )
            await state.clear()
            return

        today = _date.today()
        cal = CalendarKeyboard.build(
            year=today.year,
            month=today.month,
            available_dates=set(available_dates),
        )
        await state.set_state(BookingFSM.choosing_date)
        await msg.edit_text(
            MessageFormatter.choose_date(),
            reply_markup=cal,
            parse_mode="HTML",
        )
        await callback.answer()

    # ── Использовать прошлые данные ────────────────────────────────────────
    @router.callback_query(F.data == "use_prev")
    async def use_previous_data(callback: CallbackQuery, state: FSMContext) -> None:
        """Автозаполнение имени и телефона из последней записи."""
        appts = await asyncio.to_thread(appt_service.get_user_appointments, callback.from_user.id)
        if not appts:
            await callback.answer("Прошлых записей не найдено.", show_alert=True)
            return
        last = appts[-1]
        await state.update_data(client_name=last.client_name, phone=last.phone)
        await callback.answer("✅ Данные из прошлой записи заполнены!")
        data = await state.get_data()
        if not data.get("service"):
            await callback.message.answer(
                MessageFormatter.choose_service(),
                reply_markup=BookingKeyboard.service_selection(settings.services or None),
                parse_mode="HTML",
            )

    # ── Навигация по календарю ────────────────────────────────────────────
    @router.callback_query(BookingFSM.choosing_date, F.data.startswith("cal_prev:") | F.data.startswith("cal_next:"))
    async def calendar_navigate(callback: CallbackQuery, state: FSMContext) -> None:
        """Навигация по месяцам календаря."""
        parts = callback.data.split(":")
        direction = parts[0]
        year, month = int(parts[1]), int(parts[2])

        if direction == "cal_prev":
            month -= 1
            if month < 1:
                month = 12
                year -= 1
        else:
            month += 1
            if month > 12:
                month = 1
                year += 1

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
        # БАГ 1 FIX: проверка типа msg
        msg = callback.message
        if not isinstance(msg, Message):
            await callback.answer()
            return
        await msg.edit_reply_markup(reply_markup=cal)
        await callback.answer()

    # ── Выбор даты ────────────────────────────────────────────────────────
    @router.callback_query(BookingFSM.choosing_date, F.data.startswith("cal_day:"))
    async def choose_date(callback: CallbackQuery, state: FSMContext) -> None:
        """Показывает слоты времени для выбранной даты."""
        _, date_str = callback.data.split(":", 1)
        # БАГ 1 FIX: проверка типа msg
        msg = callback.message
        if not isinstance(msg, Message):
            await callback.answer()
            return
        slots = await sched_service.get_available_slots(date_str)
        if not slots:
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="🔔 Уведомить о свободном месте",
                    callback_data=f"join_waitlist:{date_str}"
                )
            ]])
            await callback.answer(MessageFormatter.no_available_slots(), show_alert=True)
            await msg.answer(
                MessageFormatter.no_available_slots(),
                reply_markup=kb,
                parse_mode="HTML",
            )
            return

        await state.update_data(chosen_date=date_str)
        await state.set_state(BookingFSM.choosing_time)
        await msg.edit_text(
            MessageFormatter.choose_time(),
            reply_markup=BookingKeyboard.time_slots(date_str, slots),
        )
        await callback.answer()

    # ── Игнор неактивных ячеек календаря ─────────────────────────────────
    @router.callback_query(BookingFSM.choosing_date, F.data == "calendar_ignore")
    async def calendar_empty(callback: CallbackQuery) -> None:
        await callback.answer()

    # ── Выбор времени ─────────────────────────────────────────────────────
    @router.callback_query(BookingFSM.choosing_time, F.data.startswith("slot:"))
    async def choose_time(callback: CallbackQuery, state: FSMContext) -> None:
        """Сохраняет выбранное время и запрашивает имя (или сразу комментарий)."""
        parts = callback.data.split(":", 2)
        time_str = parts[2].replace("-", ":")
        await state.update_data(chosen_time=time_str)
        # БАГ 1 FIX: проверка типа msg
        msg = callback.message
        if not isinstance(msg, Message):
            await callback.answer()
            return

        data = await state.get_data()
        # Если данные уже заполнены (из прошлой записи или переноса) — сразу к комментарию
        if data.get("client_name") and data.get("phone"):
            await state.set_state(BookingFSM.entering_comment)
            await msg.edit_text(
                MessageFormatter.enter_comment(),
                reply_markup=BookingKeyboard.skip_comment(),
                parse_mode="HTML",
            )
        else:
            await state.set_state(BookingFSM.entering_name)
            await msg.edit_text(
                MessageFormatter.enter_name(),
                parse_mode="HTML",
            )
        await callback.answer()

    # ── Ввод имени ────────────────────────────────────────────────────────
    @router.message(BookingFSM.entering_name, F.text)
    async def enter_name(message: Message, state: FSMContext) -> None:
        name = message.text.strip()
        if len(name) < 2 or len(name) > 100:
            await message.answer(MessageFormatter.invalid_name(), parse_mode="HTML")
            return
        await state.update_data(client_name=name)
        await state.set_state(BookingFSM.entering_phone)
        await message.answer(MessageFormatter.enter_phone(), parse_mode="HTML")

    # ── Ввод телефона ─────────────────────────────────────────────────────
    @router.message(BookingFSM.entering_phone, F.text)
    async def enter_phone(message: Message, state: FSMContext) -> None:
        phone = message.text.strip()
        digits = "".join(c for c in phone if c.isdigit())
        if len(digits) < 7 or len(digits) > 15:
            await message.answer(MessageFormatter.invalid_phone(), parse_mode="HTML")
            return
        if len(set(digits)) == 1:
            await message.answer(MessageFormatter.invalid_phone(), parse_mode="HTML")
            return
        normalized = re.sub(r"[\s\-()]+", "", phone)
        if not re.match(r"^\+?[0-9]{7,15}$", normalized):
            await message.answer(MessageFormatter.invalid_phone(), parse_mode="HTML")
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
        raw_comment = message.text.strip()
        if raw_comment.lower() not in skip_texts and len(raw_comment) > 500:
            await message.answer("⚠️ Комментарий слишком длинный (максимум 500 символов).")
            return
        comment = None if raw_comment.lower() in skip_texts else raw_comment
        await state.update_data(comment=comment)
        await _show_confirmation(message, state)

    @router.callback_query(BookingFSM.entering_comment, F.data == "skip_comment")
    async def skip_comment(callback: CallbackQuery, state: FSMContext) -> None:
        await state.update_data(comment=None)
        await callback.answer()
        # БАГ 1 FIX: проверка типа msg перед передачей в _show_confirmation
        msg = callback.message
        if not isinstance(msg, Message):
            return
        await _show_confirmation(msg, state)

    async def _show_confirmation(message: Message, state: FSMContext) -> None:
        """Показывает карточку записи для подтверждения."""
        data = await state.get_data()
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

    # ── Подтверждение бронирования ─────────────────────────────────────────
    @router.callback_query(BookingFSM.confirming, F.data == "booking_confirm")
    async def confirm_booking(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        # БАГ 1 FIX: проверка типа msg
        msg = callback.message
        if not isinstance(msg, Message):
            return
        data = await state.get_data()
        user_id = callback.from_user.id

        # Проверяем наличие обязательных данных
        required_keys = ("chosen_date", "chosen_time", "client_name", "phone")
        missing = [k for k in required_keys if not data.get(k)]
        if missing:
            await state.clear()
            await msg.answer(
                "⚠️ Данные записи устарели (бот мог быть перезапущен).\n"
                "Пожалуйста, начните запись заново: нажмите «💅 Записаться» 🌸"
            )
            return

        try:
            appointment_id = await asyncio.to_thread(
                appt_service.create_appointment,
                user_id,
                data["chosen_date"],
                data["chosen_time"],
                data["client_name"],
                data["phone"],
                data.get("comment"),
                callback.from_user.username,
                data.get("service"),
            )

            # FIXED BUG-10: логика переноса записи удалена из этого места.
            # Перенос полностью обрабатывается в extended_features_handler.py
            # (transfer_confirm_new_slot), где реализован корректный атомарный подход
            # с восстановлением старой записи в случае ошибки.
            # Запись через confirm_booking используется только для новых записей.

            # Уведомляем администратора
            await notif_service.notify_admin_new_booking(appointment_id)

            # Планируем напоминание клиенту
            reminder_service.schedule_reminder(
                appointment_id=appointment_id,
                user_id=user_id,
                date_str=data["chosen_date"],
                time_str=data["chosen_time"],
                timezone_str=settings.timezone,
            )

            is_admin = user_id in settings.admin_ids
            portfolio = _get_portfolio(settings)

            # Тёплое подтверждение
            success_text = MessageFormatter.booking_success(
                data["chosen_date"],
                data["chosen_time"],
                hours_before=settings.reminder_hours_before,
                client_name=data.get("client_name", ""),
            )
            await msg.edit_text(success_text, parse_mode="HTML")
            await msg.answer(
                MessageFormatter.main_menu_title(),
                reply_markup=MainMenuKeyboard.main(is_admin=is_admin, portfolio_url=portfolio),
            )

        except SlotAlreadyBookedError:
            await msg.answer(MessageFormatter.slot_already_taken())
        except Exception as exc:
            from src.domain.exceptions.appointment import (
                BlacklistedUserError,
                MaxAppointmentsReachedError,
            )
            if isinstance(exc, BlacklistedUserError):
                await msg.answer(MessageFormatter.user_blocked())
            elif isinstance(exc, MaxAppointmentsReachedError):
                await msg.answer(MessageFormatter.max_appointments_reached(exc.max_count))
            else:
                logger.error("Ошибка создания записи для %s: %s", user_id, exc)
                await msg.answer(MessageFormatter.error_general())
        finally:
            try:
                await state.clear()
            except Exception:
                logger.exception("Не удалось очистить FSM state при confirm_booking")

    @router.callback_query(BookingFSM.confirming, F.data == "booking_cancel")
    async def cancel_booking(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        is_admin = callback.from_user.id in settings.admin_ids
        portfolio = _get_portfolio(settings)
        # БАГ 1 FIX: проверка типа msg
        msg = callback.message
        if not isinstance(msg, Message):
            await callback.answer()
            return
        await msg.edit_text(MessageFormatter.booking_cancelled_by_user())
        await msg.answer(
            MessageFormatter.main_menu_title(),
            reply_markup=MainMenuKeyboard.main(is_admin=is_admin, portfolio_url=portfolio),
        )
        await callback.answer()

    # ── Мои записи ────────────────────────────────────────────────────────
    @router.message(F.text == "📋 Мои записи")
    async def my_appointments(message: Message) -> None:
        """Показывает список активных записей клиента."""

        # BUG 2.1 FIX: используем общую функцию check_subscription из common_handler
        is_subscribed = await check_subscription(message.from_user.id, message.bot, settings)
        if not is_subscribed:
            # БАГ 2 FIX: required_channel может быть None — добавляем guard
            if not settings.required_channel:
                await message.answer("❌ Подписка на канал не настроена")
                return
            await message.answer(
                MessageFormatter.error_subscription_required(settings.required_channel),
                reply_markup=MainMenuKeyboard.subscribe(settings.required_channel),
                parse_mode="HTML",
            )
            return

        user_id = message.from_user.id
        appointments = await asyncio.to_thread(appt_service.get_user_appointments, user_id)
        if not appointments:
            await message.answer(
                MessageFormatter.my_appointments_empty(),
                parse_mode="HTML",
            )
            return

        text = MessageFormatter.my_appointments_list_blocks(appointments)
        await message.answer(
            text,
            reply_markup=BookingKeyboard.cancel_appointment_list(appointments),
            parse_mode="HTML",
        )

    # ── Напоминание: кнопка «Буду!» ───────────────────────────────────────
    @router.callback_query(F.data.startswith("reminder_yes:"))
    async def reminder_yes(callback: CallbackQuery) -> None:
        appt_id = int(callback.data.split(":")[1])
        await callback.answer("Отлично, ждём тебя! 🌸")
        try:
            await asyncio.to_thread(appt_service.mark_reminder_sent, appt_id)
        except Exception:
            logger.exception("Failed to mark reminder as sent for %s", appt_id)

    # ── Напоминание: кнопка «Отменить запись» ────────────────────────────
    @router.callback_query(F.data.startswith("reminder_no:"))
    async def reminder_no(callback: CallbackQuery) -> None:
        appt_id = int(callback.data.split(":")[1])
        try:
            appt = await asyncio.to_thread(appt_service.get_appointment_by_id, appt_id)
            if not appt or appt.user_id != callback.from_user.id:
                await callback.answer(MessageFormatter.appointment_not_found(), show_alert=True)
                return
            await asyncio.to_thread(appt_service.cancel_by_id, appt_id)
            await notif_service.notify_admin_cancellation(appt_id)
            await callback.answer("Запись отменена. Надеемся увидеть тебя в другой раз! 🌸")
            # БАГ 1 FIX: проверка типа msg
            msg_r = callback.message
            if isinstance(msg_r, Message):
                await msg_r.edit_text(
                    "✅ Запись отменена.\n\nЕсли захочешь перезаписаться — нажми «💅 Записаться» 🌸"
                )
        except Exception:
            logger.exception("Failed to cancel appointment via reminder: %s", appt_id)
            await callback.answer(MessageFormatter.error_general(), show_alert=True)

    # ── Отмена записи (из списка «Мои записи») ────────────────────────────
    @router.callback_query(F.data.startswith("cancel_appt:"))
    async def cancel_appointment(callback: CallbackQuery) -> None:
        """Отменяет запись и обновляет список.

        BUG 25 FIX: после успешной отмены пользователь видит обновлённый список
        активных записей или сообщение об отсутствии записей — вместо неактивного
        сообщения об отмене без возможности вернуться к списку.
        """
        appt_id = int(callback.data.split(":")[1])
        answered = False
        # БАГ 1 FIX: проверка типа msg
        msg = callback.message
        if not isinstance(msg, Message):
            await callback.answer()
            return
        try:
            await asyncio.to_thread(appt_service.cancel_appointment, appt_id, callback.from_user.id)
            await notif_service.notify_admin_cancellation(appt_id)

            # BUG 25 FIX: после отмены показываем актуальный список записей
            user_id = callback.from_user.id
            remaining = await asyncio.to_thread(appt_service.get_user_appointments, user_id)
            cancel_text = MessageFormatter.appointment_cancel_success()
            if remaining:
                # Ещё есть активные записи — показываем обновлённый список
                await msg.edit_text(
                    cancel_text + "\n\n" + MessageFormatter.my_appointments_list_blocks(remaining),
                    reply_markup=BookingKeyboard.cancel_appointment_list(remaining),
                    parse_mode="HTML",
                )
            else:
                # Нет активных записей — кнопка записаться снова
                await msg.edit_text(
                    cancel_text,
                    reply_markup=BookingKeyboard.book_again(),
                )
            await callback.answer()
            answered = True
        except _ApptAlreadyCancelledError:
            await callback.answer("ℹ️ Эта запись уже была отменена ранее.", show_alert=True)
            answered = True
        except _ApptNotFoundError:
            await callback.answer(MessageFormatter.appointment_not_found(), show_alert=True)
            answered = True
        except Exception as exc:
            logger.warning("Не удалось отменить запись %s: %s", appt_id, exc)
            await callback.answer(MessageFormatter.appointment_not_found(), show_alert=True)
            answered = True
        finally:
            if not answered:
                await callback.answer()

    # ── FIXED BUG-1: Хендлер waitlist_book (бронирование из листа ожидания) ─
    @router.callback_query(F.data.startswith("waitlist_book:"))
    async def waitlist_book(callback: CallbackQuery, state: FSMContext) -> None:
        """FIXED BUG-1: обрабатывает кнопку 'Записаться!' из уведомления листа ожидания.

        Парсит дату и время из callback_data, проверяет что слот ещё свободен,
        и запускает процесс бронирования.
        """
        # Формат: waitlist_book:{date}:{time_with_dashes}
        parts = callback.data.split(":", 2)
        if len(parts) < 3:
            await callback.answer("❌ Некорректные данные", show_alert=True)
            return

        date_str = parts[1]
        time_str = parts[2].replace("-", ":")  # восстанавливаем HH:MM из HH-MM

        # Проверяем что слот ещё свободен
        slots = await sched_service.get_available_slots(date_str)
        available_times = [s.time for s in slots]
        if time_str not in available_times:
            await callback.answer(
                f"😔 К сожалению, слот {date_str} {time_str} уже занят.\n"
                "Выберите другое время.",
                show_alert=True,
            )
            return

        # Получаем данные предыдущей записи для автозаполнения
        prev_appts = await asyncio.to_thread(appt_service.get_user_appointments, callback.from_user.id)
        if prev_appts:
            last = prev_appts[-1]
            await state.update_data(
                client_name=last.client_name,
                phone=last.phone,
                chosen_date=date_str,
                chosen_time=time_str,
            )
        else:
            await state.update_data(chosen_date=date_str, chosen_time=time_str)

        await state.set_state(BookingFSM.choosing_service)
        # БАГ 1 FIX: проверка типа msg
        msg_w = callback.message
        if not isinstance(msg_w, Message):
            await callback.answer()
            return
        await msg_w.answer(
            f"✅ Отлично! Слот <b>{date_str} в {time_str}</b> свободен.\n\n"
            "Выберите услугу для записи:",
            reply_markup=BookingKeyboard.service_selection(settings.services or None),
            parse_mode="HTML",
        )
        await callback.answer()

    @router.callback_query(F.data == "waitlist_decline")
    async def waitlist_decline(callback: CallbackQuery) -> None:
        """Пользователь отказался от места в листе ожидания."""
        # БАГ 1 FIX: проверка типа msg
        msg_d = callback.message
        if not isinstance(msg_d, Message):
            await callback.answer()
            return
        await msg_d.edit_text(
            "Понятно! Если понадобится — заходи снова 🌸"
        )
        await callback.answer()

    # ── Возврат к выбору даты из выбора времени ────────────────────────────
    @router.callback_query(BookingFSM.choosing_time, F.data == "book_start")
    async def back_to_booking(callback: CallbackQuery, state: FSMContext) -> None:
        """Возвращает к выбору даты."""
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
        # БАГ 1 FIX: проверка типа msg
        msg = callback.message
        if not isinstance(msg, Message):
            await callback.answer()
            return
        await msg.edit_text(
            MessageFormatter.choose_date(),
            reply_markup=cal,
            parse_mode="HTML",
        )
        await callback.answer()

    return router
