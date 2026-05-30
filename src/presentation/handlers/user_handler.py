# src/presentation/handlers/user_handler.py
"""FSM-обработчики для записи клиента на маникюр."""

import logging
from datetime import date as _date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.config.dependencies import Container
from src.domain.enums.fsm_states import BookingFSM
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
        available_dates = await sched_service.get_available_dates_async()
        if not available_dates:
            is_admin = message.from_user.id in settings.admin_ids
            portfolio = _get_portfolio(settings)
            await message.answer(
                MessageFormatter.no_available_dates(),
                reply_markup=MainMenuKeyboard.main(
                    is_admin=is_admin,
                    portfolio_url=portfolio,
                ),
            )
            return

        today = _date.today()
        cal = CalendarKeyboard.build(
            year=today.year,
            month=today.month,
            available_dates=set(available_dates),
        )
        await state.set_state(BookingFSM.choosing_date)
        await message.answer(MessageFormatter.choose_date(), reply_markup=cal)

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
    @router.callback_query(BookingFSM.choosing_date, F.data.startswith("cal_day:"))
    async def choose_date(callback: CallbackQuery, state: FSMContext) -> None:
        _, date_str = callback.data.split(":", 1)
        slots = await sched_service.get_available_slots(date_str)
        if not slots:
            await callback.answer(MessageFormatter.no_available_slots(), show_alert=True)
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
        await state.set_state(BookingFSM.entering_name)
        await callback.message.edit_text(
            MessageFormatter.enter_name(),
            reply_markup=None,
        )
        await callback.answer()

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
        # Простая валидация: хотя бы 7 цифр
        digits = "".join(c for c in phone if c.isdigit())
        if len(digits) < 7:
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
        text = MessageFormatter.booking_confirmation(
            date_str=data["chosen_date"],
            time_str=data["chosen_time"],
            client_name=data["client_name"],
            phone=data["phone"],
            comment=data.get("comment"),
        )
        await state.set_state(BookingFSM.confirming)
        await message.answer(
            text,
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
        try:
            appointment_id = appt_service.create_appointment(
                user_telegram_id=user_id,
                date_str=data["chosen_date"],
                time_str=data["chosen_time"],
                client_name=data["client_name"],
                phone=data["phone"],
                comment=data.get("comment"),
            )
            # Уведомить администратора о новой записи
            await notif_service.notify_admin_new_booking(appointment_id)
            # Запланировать напоминание клиенту
            reminder_service.schedule_reminder(
                appointment_id=appointment_id,
                user_id=user_id,
                date_str=data["chosen_date"],
                time_str=data["chosen_time"],
            )
            await state.clear()
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
            await callback.message.answer(
                MessageFormatter.main_menu_title(),
                reply_markup=MainMenuKeyboard.main(is_admin=is_admin, portfolio_url=portfolio),
            )
        except SlotAlreadyBookedError:
            await callback.message.answer(MessageFormatter.slot_already_taken())
        except MaxAppointmentsReachedError as e:
            await callback.message.answer(
                MessageFormatter.max_appointments_reached(e.max_count),
            )
        except Exception as exc:
            logger.error("Ошибка создания записи для %s: %s", user_id, exc)
            await callback.message.answer(MessageFormatter.error_general())

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
        user_id = message.from_user.id
        appointments = appt_service.get_user_appointments(user_id)
        if not appointments:
            await message.answer(MessageFormatter.my_appointments_empty())
            return
        text = MessageFormatter.my_appointments_list(appointments)
        await message.answer(
            text,
            reply_markup=BookingKeyboard.cancel_appointment_list(appointments),
            parse_mode="HTML",
        )

    @router.callback_query(F.data.startswith("cancel_appt:"))
    async def cancel_appointment(callback: CallbackQuery) -> None:
        appt_id = int(callback.data.split(":")[1])
        try:
            await appt_service.cancel_appointment(appt_id, callback.from_user.id)
            # Уведомляем администратора об отмене
            await notif_service.notify_admin_cancellation(appt_id)
            await callback.message.edit_text(
                MessageFormatter.appointment_cancel_success(),
                reply_markup=None,
            )
        except Exception as exc:
            logger.warning("Не удалось отменить запись %s: %s", appt_id, exc)
            await callback.answer(MessageFormatter.appointment_not_found(), show_alert=True)
        finally:
            await callback.answer()

    return router
