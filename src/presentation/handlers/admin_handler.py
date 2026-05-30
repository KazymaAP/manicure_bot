# src/presentation/handlers/admin_handler.py
"""FSM-обработчики для администратора."""

import logging
import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.config.dependencies import Container
from src.domain.enums.fsm_states import AdminFSM
from src.presentation.formatters.message_formatter import MessageFormatter
from src.presentation.keyboards.admin import AdminKeyboard

logger = logging.getLogger(__name__)

router = Router(name="admin")


def setup_admin_router(container: Container) -> Router:  # noqa: C901
    """Фабрика роутера — привязывает сервисы к хэндлерам."""

    appt_service = container.appointment_service
    sched_service = container.schedule_service
    notif_service = container.notification_service
    reminder_service = container.reminder_service
    settings = container.settings

    def _is_admin(user_id: int) -> bool:
        return user_id in settings.admin_ids

    # ── /admin — вход в панель ────────────────────────────────────────────
    @router.message(Command("admin"))
    async def cmd_admin(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            await message.answer(MessageFormatter.admin_not_authorized())
            return
        await message.answer(
            MessageFormatter.admin_welcome(),
            reply_markup=AdminKeyboard.main_menu(),
            parse_mode="HTML",
        )

    @router.message(F.text == "⚙️ Админ-панель")
    async def btn_admin_panel(message: Message) -> None:
        """Обработчик кнопки «⚙️ Админ-панель» из главного меню."""
        if not _is_admin(message.from_user.id):
            await message.answer(MessageFormatter.admin_not_authorized())
            return
        await message.answer(
            MessageFormatter.admin_welcome(),
            reply_markup=AdminKeyboard.main_menu(),
            parse_mode="HTML",
        )

    # ── Все записи ────────────────────────────────────────────────────────
    @router.message(F.text == "📋 Все записи")
    async def admin_all_appointments(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        await message.answer(
            MessageFormatter.admin_choose_filter(),
            reply_markup=AdminKeyboard.appointments_filter(),
        )

    @router.callback_query(F.data.startswith("admin_filter:"))
    async def admin_filter_appointments(callback: CallbackQuery) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        filter_key = callback.data.split(":")[1]
        filter_names = {
            "today": "сегодня",
            "week": "за неделю",
            "active": "активные",
            "all": "все",
        }
        appointments = appt_service.get_appointments_filtered(filter_key)
        if not appointments:
            await callback.message.edit_text(MessageFormatter.admin_appointments_empty())
        else:
            text = MessageFormatter.admin_appointments_list(
                appointments, filter_name=filter_names.get(filter_key, filter_key)
            )
            await callback.message.edit_text(text, parse_mode="HTML")
        await callback.answer()

    # ── Отменить запись ───────────────────────────────────────────────────
    @router.message(F.text == "❌ Отменить запись")
    async def admin_cancel_request(message: Message, state: FSMContext) -> None:
        if not _is_admin(message.from_user.id):
            return
        await state.set_state(AdminFSM.waiting_for_appointment_id)
        await message.answer(
            "Введите <b>ID записи</b> для отмены:",
            reply_markup=AdminKeyboard.cancel(),
            parse_mode="HTML",
        )

    @router.message(AdminFSM.waiting_for_appointment_id, F.text)
    async def admin_cancel_by_id(message: Message, state: FSMContext) -> None:
        if message.text.strip() == "❌ Отмена":
            await state.clear()
            await message.answer(
                MessageFormatter.operation_cancelled(),
                reply_markup=AdminKeyboard.main_menu(),
            )
            return
        try:
            appt_id = int(message.text.strip())
        except ValueError:
            await message.answer(MessageFormatter.invalid_appointment_id())
            return

        appt = appt_service.get_appointment_by_id(appt_id)
        if not appt:
            await message.answer(MessageFormatter.appointment_not_found())
            await state.clear()
            return

        await state.update_data(cancel_appointment_id=appt_id)
        await message.answer(
            MessageFormatter.admin_appointment_detail(appt),
            reply_markup=AdminKeyboard.confirm_cancel(appt_id),
            parse_mode="HTML",
        )
        await state.set_state(AdminFSM.confirming_cancel)

    @router.callback_query(F.data.startswith("admin_confirm_cancel:"))
    async def admin_confirm_cancel(callback: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer("Нет прав администратора.", show_alert=True)
            return
        appt_id = int(callback.data.split(":")[1])
        appt = appt_service.get_appointment_by_id(appt_id)
        try:
            appt_service.admin_cancel_appointment(appt_id)
            await callback.message.edit_text(
                MessageFormatter.admin_cancel_success(appt_id, appt.client_name if appt else "?"),
                reply_markup=None,
            )
            # Уведомляем клиента и отменяем напоминание
            if appt:
                try:
                    await notif_service.notify_client_cancellation_by_admin(
                        appt.user_id, appt.date, appt.time
                    )
                    if appt.id is not None:
                        reminder_service.cancel_reminder(appt.id)
                except Exception as notify_exc:
                    logger.warning(
                        "Не удалось уведомить клиента user_id=%s об отмене: %s",
                        appt.user_id, notify_exc,
                    )
        except Exception as exc:
            logger.error("Ошибка отмены записи #%s: %s", appt_id, exc)
            await callback.message.edit_text(MessageFormatter.error_general())
        finally:
            await state.clear()
            await callback.answer()

    @router.callback_query(F.data.startswith("admin_cancel_abort:"))
    async def admin_cancel_abort(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await callback.message.edit_text(MessageFormatter.operation_cancelled())
        await callback.answer()

    # ── Расписание ────────────────────────────────────────────────────────
    @router.message(F.text == "📅 Расписание")
    async def admin_schedule(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        dates = await sched_service.get_all_working_dates()
        if not dates:
            await message.answer(MessageFormatter.admin_schedule_empty())
            return
        await message.answer(
            MessageFormatter.admin_choose_date(),
            reply_markup=AdminKeyboard.schedule_dates(dates),
        )

    @router.callback_query(F.data.startswith("admin_date:"))
    async def admin_date_detail(callback: CallbackQuery) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        date_str = callback.data.split(":", 1)[1]
        slots = await sched_service.get_slots_for_date(date_str)
        await callback.message.edit_text(
            MessageFormatter.admin_day_schedule(date_str, slots),
            reply_markup=AdminKeyboard.day_slots(date_str, [s.time for s in slots]),
            parse_mode="HTML",
        )
        await callback.answer()

    # ── Добавить слот ─────────────────────────────────────────────────────
    @router.message(F.text == "➕ Добавить слот")
    async def admin_add_slot_start(message: Message, state: FSMContext) -> None:
        if not _is_admin(message.from_user.id):
            return
        await state.set_state(AdminFSM.waiting_for_date)
        await message.answer(
            MessageFormatter.admin_enter_date(),
            reply_markup=AdminKeyboard.cancel(),
            parse_mode="HTML",
        )

    @router.callback_query(F.data.startswith("admin_add_slot:"))
    async def admin_add_slot_from_cb(callback: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        date_str = callback.data.split(":", 1)[1]
        await state.update_data(slot_date=date_str)
        await state.set_state(AdminFSM.waiting_for_time)
        await callback.message.answer(
            MessageFormatter.admin_enter_slot_time(),
            reply_markup=AdminKeyboard.cancel(),
            parse_mode="HTML",
        )
        await callback.answer()

    @router.message(AdminFSM.waiting_for_date, F.text)
    async def admin_add_slot_date(message: Message, state: FSMContext) -> None:
        if message.text.strip() == "❌ Отмена":
            await state.clear()
            await message.answer(
                MessageFormatter.operation_cancelled(),
                reply_markup=AdminKeyboard.main_menu(),
            )
            return

        text = message.text.strip()
        # Допускаем форматы YYYY-MM-DD и YYYY.MM.DD
        if not re.match(r"^\d{4}[-.]\d{2}[-.]\d{2}$", text):
            await message.answer(MessageFormatter.admin_invalid_date_format())
            return

        # Нормализуем точечные разделители -> дефисы
        date_str = text.replace('.', '-')

        # Если это поток открытия/закрытия дня — обрабатываем отдельно
        data = await state.get_data()
        if data.get("is_opening") is not None:
            is_opening = bool(data.get("is_opening"))
            try:
                # Попытаемся получить день
                day = sched_service._schedule_repo.get_working_day(date_str)
                if is_opening:
                    if not day:
                        # Создаём день с дефолтными слотами
                        sched_service._schedule_repo.add_working_day(date_str, list(settings.default_time_slots))
                        sched_service._schedule_repo.set_day_status(date_str, is_closed=False)
                    else:
                        # Если день есть, просто откроем его
                        sched_service._schedule_repo.set_day_status(date_str, is_closed=False)
                    await message.answer(MessageFormatter.admin_day_opened(date_str), reply_markup=AdminKeyboard.main_menu(), parse_mode="HTML")
                else:
                    if not day:
                        # Создаём день и сразу закроем его (чтобы он появился в списке как закрытый)
                        sched_service._schedule_repo.add_working_day(date_str, list(settings.default_time_slots))
                    sched_service._schedule_repo.set_day_status(date_str, is_closed=True)
                    await message.answer(MessageFormatter.admin_day_closed(date_str), reply_markup=AdminKeyboard.main_menu(), parse_mode="HTML")
            except Exception as exc:
                logger.error("Ошибка при открытии/закрытии дня %s: %s", date_str, exc)
                await message.answer(MessageFormatter.error_general())
            finally:
                await state.clear()
            return

        # Иначе — стандартный поток добавления слота
        # Убедимся, что рабочий день существует — иначе добавленный слот не будет виден в списках
        try:
            day = sched_service._schedule_repo.get_working_day(date_str)
            if not day:
                # Создаём пустой рабочий день (слоты добавим ниже), чтобы он появился в списке
                sched_service._schedule_repo.add_working_day(date_str, [])
        except Exception as exc:
            logger.warning("Не удалось проверить/создать рабочий день %s: %s", date_str, exc)

        await state.update_data(slot_date=date_str)
        await state.set_state(AdminFSM.waiting_for_time)
        await message.answer(
            MessageFormatter.admin_enter_slot_time(),
            reply_markup=AdminKeyboard.cancel(),
            parse_mode="HTML",
        )

    @router.message(AdminFSM.waiting_for_time, F.text)
    async def admin_add_slot_time(message: Message, state: FSMContext) -> None:
        if message.text.strip() == "❌ Отмена":
            await state.clear()
            await message.answer(
                MessageFormatter.operation_cancelled(),
                reply_markup=AdminKeyboard.main_menu(),
            )
            return
        time_str = message.text.strip()
        if not re.match(r"^\d{2}:\d{2}$", time_str):
            await message.answer(MessageFormatter.admin_invalid_time_format())
            return
        data = await state.get_data()
        date_str = data["slot_date"]
        try:
            await sched_service.add_slot(date_str, time_str)
            await message.answer(
                MessageFormatter.admin_slot_added(date_str, time_str),
                reply_markup=AdminKeyboard.main_menu(),
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.warning("Ошибка добавления слота %s %s: %s", date_str, time_str, exc)
            await message.answer(MessageFormatter.admin_slot_already_exists())
        await state.clear()

    # ── Удалить слот (inline) ─────────────────────────────────────────────
    @router.callback_query(F.data.startswith("admin_del_slot:"))
    async def admin_delete_slot(callback: CallbackQuery) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        _, date_str, time_str = callback.data.split(":", 2)
        await callback.message.edit_reply_markup(
            reply_markup=AdminKeyboard.confirm_delete_slot(date_str, time_str)
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin_confirm_del_slot:"))
    async def admin_confirm_delete_slot(callback: CallbackQuery) -> None:
        _, date_str, time_str = callback.data.split(":", 2)
        try:
            await sched_service.remove_slot(date_str, time_str)
            await callback.message.edit_text(
                MessageFormatter.admin_slot_deleted(date_str, time_str),
                reply_markup=None,
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.error("Ошибка удаления слота: %s", exc)
            await callback.message.edit_text(MessageFormatter.error_general())
        await callback.answer()

    # ── Открыть / закрыть день ────────────────────────────────────────────
    @router.message(F.text.in_({"🗓 Открыть день", "🔒 Закрыть день"}))
    async def admin_toggle_day_start(message: Message, state: FSMContext) -> None:
        if not _is_admin(message.from_user.id):
            return
        is_opening = message.text == "🗓 Открыть день"
        await state.update_data(is_opening=is_opening)
        await state.set_state(AdminFSM.waiting_for_date)
        await message.answer(
            MessageFormatter.admin_enter_date(),
            reply_markup=AdminKeyboard.cancel(),
            parse_mode="HTML",
        )

    @router.callback_query(F.data.startswith("admin_toggle_day:"))
    async def admin_toggle_day(callback: CallbackQuery) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        date_str = callback.data.split(":", 1)[1]
        try:
            result = await sched_service.toggle_working_day(date_str)
            if result:
                text = MessageFormatter.admin_day_opened(date_str)
            else:
                text = MessageFormatter.admin_day_closed(date_str)
            await callback.message.edit_text(text, reply_markup=None, parse_mode="HTML")
        except Exception as exc:
            logger.error("Ошибка переключения дня: %s", exc)
            await callback.message.edit_text(MessageFormatter.error_general())
        await callback.answer()

    # ── Статистика ────────────────────────────────────────────────────────
    @router.message(F.text == "📊 Статистика")
    async def admin_stats(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        try:
            stats = appt_service.get_statistics()
            await message.answer(
                MessageFormatter.admin_stats(
                    total=stats.get("total", 0),
                    confirmed=stats.get("confirmed", 0),
                    cancelled=stats.get("cancelled", 0),
                    today=stats.get("today", 0),
                    week=stats.get("week", 0),
                ),
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.error("Ошибка получения статистики: %s", exc)
            await message.answer(MessageFormatter.error_general())

    # ── Навигация назад ───────────────────────────────────────────────────
    @router.callback_query(F.data == "admin_back_main")
    async def admin_back_main(callback: CallbackQuery) -> None:
        await callback.message.edit_text(
            MessageFormatter.admin_welcome(),
            reply_markup=None,
            parse_mode="HTML",
        )
        await callback.answer()

    @router.callback_query(F.data == "admin_back_schedule")
    async def admin_back_schedule(callback: CallbackQuery) -> None:
        dates = await sched_service.get_all_working_dates()
        await callback.message.edit_text(
            "Выберите дату для управления:",
            reply_markup=AdminKeyboard.schedule_dates(dates),
        )
        await callback.answer()

    return router
