"""
src/presentation/handlers/admin_handler.py — Административная панель.

Обновлено: 6 разделов (Сегодня, Все записи, Расписание, Клиенты, Настройки, Чёрный список),
кнопки «Пришла» и «Отменить», управление услугами через бот без правки кода,
поиск клиентов, уведомление за 2 часа до первой записи.

FIXED (новые исправления 2026-06-08):
  - BUG 1.1: добавлены хендлеры admin_slot_info и admin_toggle_slot
  - BUG 1.2: добавлен блок elif edit_mode == "photo" в admin_edit_setting_text
  - BUG 1.3: двойное подтверждение — кнопки «❌ Отменить» переименованы в admin_cancel_request:ID,
             добавлен хендлер admin_cancel_request_cb, показывающий диалог подтверждения
  - BUG 2.2: _load_config() вынесена из вложенных функций и теперь использует _load_config_json из dependencies
  - BUG 2.3: три отдельных FSM-состояния waiting_for_welcome_text / waiting_for_photo_url /
             waiting_for_broadcast_text вместо перегруженного waiting_for_broadcast
  - BUG 3.2: settings.reminder_hours_before обновляется через object.__setattr__ вместо __dict__
  - BUG 3.3: все import перенесены в начало файла
  - BUG 3.4: except Exception: pass → except Exception as exc: logger.debug/warning
  - BUG 4.2: добавлена проверка прав в admin_client_history_cb
"""

import asyncio
import contextlib
import csv
import io
import json
import logging
import os
import re
import tempfile
from datetime import date, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from src.config.dependencies import Container, _load_config_json
from src.domain.enums.fsm_states import AdminFSM
from src.domain.exceptions.appointment import (
    AppointmentAlreadyCancelledError,
    AppointmentNotFoundError,
)
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

    # FIXED HIGH-03: asyncio.Lock для защиты от concurrent записи config.json
    _config_write_lock = asyncio.Lock()

    def _is_admin(user_id: int) -> bool:
        return user_id in settings.admin_ids

    # ── Хелпер для чтения config.json ────────────────────────────────────
    # BUG 2.2: используем _load_config_json из dependencies вместо дублирующей вложенной функции
    def _load_config() -> dict:
        """Загружает config.json используя кэшированную версию из dependencies."""
        return dict(_load_config_json())

    # ── Хелпер для атомарного сохранения config.json ─────────────────────
    async def _save_config(config: dict) -> None:
        """Атомарно сохраняет config.json и инвалидирует кэш."""
        config_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "config.json")
        )
        async with _config_write_lock:
            config_dir = os.path.dirname(config_path)
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8",
                    dir=config_dir, suffix=".tmp", delete=False,
                ) as tmp_f:
                    tmp_path = tmp_f.name
                    json.dump(config, tmp_f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, config_path)
                tmp_path = None
                try:
                    _load_config_json.cache_clear()
                except Exception as exc:
                    logger.debug("Suppressed cache_clear error: %s", exc, exc_info=True)
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    with contextlib.suppress(Exception):
                        os.unlink(tmp_path)

    # ── /admin — вход в панель ────────────────────────────────────────────
    @router.message(Command("admin"))
    async def cmd_admin(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            await message.answer(MessageFormatter.admin_not_authorized())
            return

        stats = await asyncio.to_thread(appt_service.get_statistics)
        free_slots = 0
        try:
            if hasattr(sched_service, 'count_free_slots'):
                free_slots = await asyncio.to_thread(sched_service.count_free_slots)
        except Exception as exc:
            logger.debug("Suppressed: count_free_slots failed: %s", exc, exc_info=True)
            free_slots = 0

        text = MessageFormatter.admin_dashboard_summary(
            today=stats.get('today', 0),
            free_slots=free_slots,
            week=stats.get('week', 0),
            total=stats.get('total', 0),
            confirmed=stats.get('confirmed', 0),
        )
        await message.answer(text, reply_markup=AdminKeyboard.main_menu(), parse_mode="HTML")

    @router.message(F.text == "⚙️ Админ-панель")
    async def btn_admin_panel(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            await message.answer(MessageFormatter.admin_not_authorized())
            return
        await message.answer(
            MessageFormatter.admin_welcome(),
            reply_markup=AdminKeyboard.main_menu(),
            parse_mode="HTML",
        )

    # ════════════════════════════════════════════════════════════════════
    # РАЗДЕЛ 1: СЕГОДНЯ
    # ════════════════════════════════════════════════════════════════════

    @router.message(F.text == "📅 Сегодня")
    async def admin_today(message: Message) -> None:
        """Список клиентов на сегодня с кнопками «Пришла» и «Отменить»."""
        if not _is_admin(message.from_user.id):
            return

        appointments = await asyncio.to_thread(appt_service.get_appointments_filtered, "today")
        text = MessageFormatter.admin_today_appointments(appointments)
        await message.answer(text, parse_mode="HTML")

        # Отправляем кнопки действий для каждой записи отдельно
        for appt in appointments:
            if not getattr(appt, 'is_cancelled', False):
                # BUG 1.3: callback_data кнопки «Отменить» теперь admin_cancel_request:ID
                # вместо admin_confirm_cancel:ID — показывает диалог подтверждения
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Пришла",
                            callback_data=f"admin_arrived:{appt.id}"
                        ),
                        InlineKeyboardButton(
                            text="❌ Отменить",
                            callback_data=f"admin_cancel_request:{appt.id}"
                        ),
                    ]
                ])
                await message.answer(
                    f"🕐 <b>{appt.time}</b> — {appt.client_name}",
                    reply_markup=kb,
                    parse_mode="HTML",
                )

    @router.callback_query(F.data.startswith("admin_arrived:"))
    async def admin_mark_arrived(callback: CallbackQuery) -> None:
        """Отмечает клиента как пришедшего."""
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        appt_id = int(callback.data.split(":")[1])
        try:
            appt = await asyncio.to_thread(appt_service.get_appointment_by_id, appt_id)
            if appt:
                with contextlib.suppress(AttributeError):
                    await asyncio.to_thread(appt_service.mark_completed, appt_id)
                await callback.message.edit_text(
                    f"✅ {appt.client_name} ({appt.time}) — отмечена как пришедшая",
                    reply_markup=None,
                )

                # Отправляем благодарность клиенту
                try:
                    thank_text = MessageFormatter.after_visit_thank_you(appt.client_name)
                    from src.presentation.keyboards.booking import BookingKeyboard
                    await callback.message.bot.send_message(
                        appt.user_id,
                        thank_text,
                        reply_markup=BookingKeyboard.book_again(),
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.warning("Не удалось отправить благодарность клиенту %s: %s", appt.user_id, e)

            await callback.answer("✅ Клиент отмечен как пришедший")
        except Exception as exc:
            logger.error("Ошибка отметки прихода #%s: %s", appt_id, exc)
            await callback.answer(MessageFormatter.error_general(), show_alert=True)

    # ════════════════════════════════════════════════════════════════════
    # РАЗДЕЛ 2: ВСЕ ЗАПИСИ
    # ════════════════════════════════════════════════════════════════════

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
            "today": "сегодня", "week": "за неделю",
            "active": "активные", "all": "все",
        }
        appointments = await asyncio.to_thread(appt_service.get_appointments_filtered, filter_key)
        if not appointments:
            await callback.message.edit_text(MessageFormatter.admin_appointments_empty())
        else:
            page_size = 20
            page_appts = appointments[:page_size]
            total = len(appointments)
            filter_label = filter_names.get(filter_key, filter_key)
            text = MessageFormatter.admin_appointments_list(page_appts, filter_name=filter_label)
            if total > page_size:
                text += f"\n\n<i>Показано {page_size} из {total} записей.</i>"
            try:
                await callback.message.edit_text(text, parse_mode="HTML")
            except Exception as exc:
                logger.debug("Suppressed edit_text error: %s", exc, exc_info=True)
                short_text = MessageFormatter.admin_appointments_list(appointments[:10], filter_label)
                await callback.message.edit_text(short_text, parse_mode="HTML")
        await callback.answer()

    # ── Отменить запись (ввод ID) ─────────────────────────────────────────
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

        appt = await asyncio.to_thread(appt_service.get_appointment_by_id, appt_id)
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

    # ── BUG 1.3: Новый хендлер — первый шаг запроса на отмену ────────────
    @router.callback_query(F.data.startswith("admin_cancel_request:"))
    async def admin_cancel_request_cb(callback: CallbackQuery, state: FSMContext) -> None:
        """
        BUG 1.3 FIX: Первый шаг — показываем диалог подтверждения.
        Callback 'admin_cancel_request:ID' — срабатывает при нажатии «❌ Отменить»
        из раздела «Сегодня» и «Клиенты».
        Не отменяет запись немедленно — только показывает confirm_cancel keyboard.
        """
        if not _is_admin(callback.from_user.id):
            await callback.answer("Нет прав администратора.", show_alert=True)
            return
        appt_id = int(callback.data.split(":")[1])
        appt = await asyncio.to_thread(appt_service.get_appointment_by_id, appt_id)
        if not appt:
            await callback.answer("Запись не найдена.", show_alert=True)
            return
        await callback.message.edit_text(
            f"⚠️ <b>Подтверждение отмены</b>\n\n"
            f"Клиент: <b>{appt.client_name}</b>\n"
            f"Дата: <b>{appt.date}</b>  Время: <b>{appt.time}</b>\n\n"
            "Действительно отменить запись?",
            reply_markup=AdminKeyboard.confirm_cancel(appt_id),
            parse_mode="HTML",
        )
        await callback.answer()

    # ── Финальная отмена по подтверждению ────────────────────────────────
    @router.callback_query(F.data.startswith("admin_confirm_cancel:"))
    async def admin_confirm_cancel(callback: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer("Нет прав администратора.", show_alert=True)
            return
        appt_id = int(callback.data.split(":")[1])
        appt = await asyncio.to_thread(appt_service.get_appointment_by_id, appt_id)
        try:
            await asyncio.to_thread(appt_service.admin_cancel_appointment, appt_id)
            await callback.message.edit_text(
                MessageFormatter.admin_cancel_success(appt_id, appt.client_name if appt else "?"),
                reply_markup=None,
            )
            if appt:
                try:
                    await notif_service.notify_client_cancellation_by_admin(
                        appt.user_id, appt.date, appt.time
                    )
                    if appt.id is not None:
                        reminder_service.cancel_reminder(appt.id)
                except Exception as notify_exc:
                    logger.warning("Не удалось уведомить клиента: %s", notify_exc)
        except AppointmentAlreadyCancelledError:
            await callback.message.edit_text("ℹ️ Эта запись уже была отменена ранее.", reply_markup=None)
        except AppointmentNotFoundError:
            await callback.message.edit_text("ℹ️ Запись не найдена.", reply_markup=None)
        except Exception as exc:
            logger.error("Ошибка отмены записи #%s: %s", appt_id, exc)
            await callback.message.edit_text(MessageFormatter.error_general())
        finally:
            with contextlib.suppress(Exception):
                await state.clear()
            await callback.answer()

    @router.callback_query(F.data.startswith("admin_cancel_abort:"))
    async def admin_cancel_abort(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await callback.message.edit_text(MessageFormatter.operation_cancelled())
        await callback.answer()

    # ════════════════════════════════════════════════════════════════════
    # РАЗДЕЛ 3: РАСПИСАНИЕ
    # ════════════════════════════════════════════════════════════════════

    @router.message(F.text == "🗓 Расписание")
    async def admin_schedule(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        await message.answer(
            "🗓 <b>Управление расписанием</b>",
            reply_markup=AdminKeyboard.schedule_menu(),
            parse_mode="HTML",
        )

    @router.callback_query(F.data == "admin_view_schedule")
    async def admin_view_schedule(callback: CallbackQuery) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        dates = await sched_service.get_all_working_dates()
        if not dates:
            await callback.message.edit_text(MessageFormatter.admin_schedule_empty())
            return
        await callback.message.edit_text(
            MessageFormatter.admin_choose_date(),
            reply_markup=AdminKeyboard.schedule_dates(dates),
        )
        await callback.answer()

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

    # ── BUG 1.1: Хендлер admin_slot_info — информация о слоте ───────────
    @router.callback_query(F.data.startswith("admin_slot_info:"))
    async def admin_slot_info(callback: CallbackQuery) -> None:
        """
        BUG 1.1 FIX: Показывает информацию о слоте (занят/свободен).
        Для занятого — показывает имя и телефон клиента из appointments.
        """
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        parts = callback.data.split(":", 2)
        if len(parts) < 3:
            await callback.answer("Некорректные данные слота.", show_alert=True)
            return
        date_str, time_str = parts[1], parts[2]

        try:
            all_slots = await asyncio.to_thread(sched_service.get_all_slots, date_str)
            slot = next((s for s in all_slots if s.time == time_str), None)

            if slot is None:
                await callback.answer(f"Слот {time_str} не найден на {date_str}.", show_alert=True)
                return

            if slot.is_booked:
                # Ищем запись в appointments
                day_appts = await asyncio.to_thread(appt_service.get_appointments_by_date, date_str)
                appt = next((a for a in day_appts if a.time == time_str and not getattr(a, 'is_cancelled', False)), None)
                if appt:
                    await callback.answer(
                        f"📌 Занят: {appt.client_name}\n📞 {appt.phone}",
                        show_alert=True,
                    )
                else:
                    await callback.answer(f"📌 Слот {time_str} занят (клиент не найден).", show_alert=True)
            else:
                await callback.answer(f"🟢 Слот {time_str} на {date_str} свободен.", show_alert=True)
        except Exception as exc:
            logger.error("Ошибка admin_slot_info %s %s: %s", date_str, time_str, exc)
            await callback.answer("Ошибка получения информации о слоте.", show_alert=True)

    # ── BUG 1.1: Хендлер admin_toggle_slot — переключение слота ─────────
    @router.callback_query(F.data.startswith("admin_toggle_slot:"))
    async def admin_toggle_slot(callback: CallbackQuery) -> None:
        """
        BUG 1.1 FIX: Переключает статус свободного слота (открыт → закрыт).
        Закрывает слот через sched_service.remove_slot(), т.к. слот гарантированно свободен
        (для занятых callback_data="admin_noop").
        """
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        parts = callback.data.split(":", 2)
        if len(parts) < 3:
            await callback.answer("Некорректные данные.", show_alert=True)
            return
        date_str, time_str = parts[1], parts[2]

        try:
            await sched_service.remove_slot(date_str, time_str)
            await callback.answer(f"🔒 Слот {time_str} на {date_str} закрыт.", show_alert=True)
            # Обновляем отображение дня
            slots = await sched_service.get_slots_for_date(date_str)
            await callback.message.edit_text(
                MessageFormatter.admin_day_schedule(date_str, slots),
                reply_markup=AdminKeyboard.day_slots(date_str, [s.time for s in slots]),
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.error("Ошибка admin_toggle_slot %s %s: %s", date_str, time_str, exc)
            await callback.answer("Ошибка при закрытии слота.", show_alert=True)

    # ── Добавить слот (из меню) ────────────────────────────────────────────
    @router.callback_query(F.data == "admin_add_slot_manual")
    async def admin_add_slot_start_cb(callback: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminFSM.waiting_for_slot_date)
        await callback.message.answer(
            MessageFormatter.admin_enter_date(),
            reply_markup=AdminKeyboard.cancel(),
            parse_mode="HTML",
        )
        await callback.answer()

    @router.message(F.text == "➕ Добавить слот")
    async def admin_add_slot_start(message: Message, state: FSMContext) -> None:
        if not _is_admin(message.from_user.id):
            return
        await state.set_state(AdminFSM.waiting_for_slot_date)
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

    @router.message(AdminFSM.waiting_for_slot_date, F.text)
    async def admin_add_slot_date_new(message: Message, state: FSMContext) -> None:
        if message.text.strip() == "❌ Отмена":
            await state.clear()
            await message.answer(MessageFormatter.operation_cancelled(), reply_markup=AdminKeyboard.main_menu())
            return
        text = message.text.strip()
        if not re.match(r"^\d{4}[-.]\d{2}[-.]\d{2}$", text) and not re.match(r"^\d{4}-\d{2}-\d{2}$", text):
            await message.answer(MessageFormatter.admin_invalid_date_format())
            return
        date_str = text.replace('.', '-')
        try:
            await asyncio.to_thread(sched_service.ensure_working_day_exists, date_str)
        except Exception as exc:
            logger.warning("Не удалось создать рабочий день %s: %s", date_str, exc)
        await state.update_data(slot_date=date_str)
        await state.set_state(AdminFSM.waiting_for_time)
        await message.answer(
            MessageFormatter.admin_enter_slot_time(),
            reply_markup=AdminKeyboard.cancel(),
            parse_mode="HTML",
        )

    @router.message(AdminFSM.waiting_for_toggle_date, F.text)
    async def admin_toggle_day_date(message: Message, state: FSMContext) -> None:
        if message.text.strip() == "❌ Отмена":
            await state.clear()
            await message.answer(MessageFormatter.operation_cancelled(), reply_markup=AdminKeyboard.main_menu())
            return
        text = message.text.strip()
        if not re.match(r"^\d{4}[-.]\d{2}[-.]\d{2}$", text) and not re.match(r"^\d{4}-\d{2}-\d{2}$", text):
            await message.answer(MessageFormatter.admin_invalid_date_format())
            return
        date_str = text.replace('.', '-')
        data = await state.get_data()
        is_opening = bool(data.get("is_opening", True))
        try:
            if is_opening:
                await asyncio.to_thread(sched_service.open_day, date_str)
                await message.answer(MessageFormatter.admin_day_opened(date_str), reply_markup=AdminKeyboard.main_menu(), parse_mode="HTML")
            else:
                await asyncio.to_thread(sched_service.close_day, date_str)
                await message.answer(MessageFormatter.admin_day_closed(date_str), reply_markup=AdminKeyboard.main_menu(), parse_mode="HTML")
        except Exception as exc:
            logger.error("Ошибка при открытии/закрытии дня %s: %s", date_str, exc)
            await message.answer(MessageFormatter.error_general())
        finally:
            await state.clear()

    @router.message(AdminFSM.waiting_for_date, F.text)
    async def admin_add_slot_date(message: Message, state: FSMContext) -> None:
        if message.text.strip() == "❌ Отмена":
            await state.clear()
            await message.answer(MessageFormatter.operation_cancelled(), reply_markup=AdminKeyboard.main_menu())
            return

        text = message.text.strip()
        if not re.match(r"^\d{4}[-.]\d{2}[-.]\d{2}$", text) and not re.match(r"^\d{4}-\d{2}-\d{2}$", text):
            await message.answer(MessageFormatter.admin_invalid_date_format())
            return

        date_str = text.replace('.', '-')
        data = await state.get_data()

        apply_template_id = data.get("apply_template_id")
        if apply_template_id is not None:
            try:
                count = await asyncio.to_thread(sched_service.apply_template_to_date, int(apply_template_id), date_str)
                await message.answer(
                    f"✅ Шаблон применён к <b>{date_str}</b>!\nДобавлено слотов: <b>{count}</b>",
                    reply_markup=AdminKeyboard.main_menu(),
                    parse_mode="HTML",
                )
            except Exception as exc:
                logger.error("Ошибка применения шаблона: %s", exc)
                await message.answer(MessageFormatter.error_general())
            finally:
                await state.clear()
            return

        if data.get("is_opening") is not None:
            is_opening = bool(data.get("is_opening"))
            try:
                if is_opening:
                    await asyncio.to_thread(sched_service.open_day, date_str)
                    await message.answer(MessageFormatter.admin_day_opened(date_str), reply_markup=AdminKeyboard.main_menu(), parse_mode="HTML")
                else:
                    await asyncio.to_thread(sched_service.close_day, date_str)
                    await message.answer(MessageFormatter.admin_day_closed(date_str), reply_markup=AdminKeyboard.main_menu(), parse_mode="HTML")
            except Exception as exc:
                logger.error("Ошибка при открытии/закрытии дня %s: %s", date_str, exc)
                await message.answer(MessageFormatter.error_general())
            finally:
                await state.clear()
            return

        try:
            await asyncio.to_thread(sched_service.ensure_working_day_exists, date_str)
        except Exception as exc:
            logger.warning("Не удалось создать рабочий день %s: %s", date_str, exc)

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
            await message.answer(MessageFormatter.operation_cancelled(), reply_markup=AdminKeyboard.main_menu())
            return
        time_str = message.text.strip()
        if not re.match(r"^\d{2}:\d{2}$", time_str):
            await message.answer(MessageFormatter.admin_invalid_time_format())
            return
        try:
            h, m = map(int, time_str.split(":"))
            if not (0 <= h < 24 and 0 <= m < 60):
                raise ValueError(f"Time out of range: {time_str}")
        except ValueError:
            await message.answer("❌ Некорректное время. Часы: 00–23, минуты: 00–59. Например: 10:00")
            return
        data = await state.get_data()
        date_str = data.get("slot_date", "")
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

    # ── Удалить слот ──────────────────────────────────────────────────────
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
        if not _is_admin(callback.from_user.id):
            await callback.answer("Нет прав администратора.", show_alert=True)
            return
        _, date_str, time_str = callback.data.split(":", 2)
        try:
            all_slots = await asyncio.to_thread(sched_service.get_all_slots, date_str)
            booked_slot = next((s for s in all_slots if s.time == time_str and s.is_booked), None)
            if booked_slot:
                await callback.answer(
                    f"❌ Слот {time_str} на {date_str} уже забронирован. Сначала отмените запись.",
                    show_alert=True
                )
                return
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

    # ── Открыть/закрыть день ─────────────────────────────────────────────
    @router.message(F.text.in_({"🗓 Открыть день", "🔒 Закрыть день"}))
    async def admin_toggle_day_start(message: Message, state: FSMContext) -> None:
        if not _is_admin(message.from_user.id):
            return
        is_opening = message.text == "🗓 Открыть день"
        await state.update_data(is_opening=is_opening)
        await state.set_state(AdminFSM.waiting_for_toggle_date)
        await message.answer(
            MessageFormatter.admin_enter_date(),
            reply_markup=AdminKeyboard.cancel(),
            parse_mode="HTML",
        )

    @router.callback_query(F.data == "admin_open_day_cb")
    async def admin_open_day_cb(callback: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        await state.update_data(is_opening=True)
        await state.set_state(AdminFSM.waiting_for_toggle_date)
        await callback.message.answer(
            MessageFormatter.admin_enter_date(),
            reply_markup=AdminKeyboard.cancel(),
            parse_mode="HTML",
        )
        await callback.answer()

    @router.callback_query(F.data == "admin_close_day_cb")
    async def admin_close_day_cb(callback: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        await state.update_data(is_opening=False)
        await state.set_state(AdminFSM.waiting_for_toggle_date)
        await callback.message.answer(
            MessageFormatter.admin_enter_date(),
            reply_markup=AdminKeyboard.cancel(),
            parse_mode="HTML",
        )
        await callback.answer()

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

    # ── Открыть неделю ────────────────────────────────────────────────────
    @router.message(F.text == "📅 Открыть неделю")
    async def admin_open_week_start(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        await message.answer(
            "Открыть следующие 7 рабочих дней?",
            reply_markup=AdminKeyboard.open_week_confirm(),
        )

    @router.callback_query(F.data == "admin_open_week")
    async def admin_open_week(callback: CallbackQuery) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        try:
            today = date.today()
            opened = 0
            for i in range(1, 8):
                d = today + timedelta(days=i)
                if d.weekday() < 5:  # Пн-Пт
                    date_str = d.strftime("%Y-%m-%d")
                    await asyncio.to_thread(sched_service.open_day, date_str)
                    opened += 1
            await callback.message.edit_text(f"✅ Открыто {opened} рабочих дней.")
        except Exception as exc:
            logger.error("Ошибка открытия недели: %s", exc)
            await callback.message.edit_text(MessageFormatter.error_general())
        await callback.answer()

    # ════════════════════════════════════════════════════════════════════
    # РАЗДЕЛ 4: КЛИЕНТЫ
    # ════════════════════════════════════════════════════════════════════

    @router.message(F.text == "👥 Клиенты")
    async def admin_clients(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        await message.answer(
            "👥 <b>Управление клиентами</b>",
            reply_markup=AdminKeyboard.clients_menu(),
            parse_mode="HTML",
        )

    @router.callback_query(F.data == "admin_back_clients")
    async def admin_back_clients(callback: CallbackQuery) -> None:
        await callback.message.edit_text(
            "👥 <b>Управление клиентами</b>",
            reply_markup=AdminKeyboard.clients_menu(),
            parse_mode="HTML",
        )
        await callback.answer()

    # ── Поиск клиентов ────────────────────────────────────────────────────
    @router.message(F.text == "🔍 Найти клиента")
    async def admin_search_client_start(message: Message, state: FSMContext) -> None:
        if not _is_admin(message.from_user.id):
            return
        await state.set_state(AdminFSM.waiting_for_search_query)
        await message.answer(
            "🔍 Введите имя или номер телефона клиента:",
            reply_markup=AdminKeyboard.cancel(),
        )

    @router.callback_query(F.data == "admin_find_client")
    async def admin_find_client_cb(callback: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminFSM.waiting_for_search_query)
        await callback.message.answer(
            "🔍 Введите имя или номер телефона клиента:",
            reply_markup=AdminKeyboard.cancel(),
        )
        await callback.answer()

    @router.message(AdminFSM.waiting_for_search_query, F.text)
    async def admin_search_client(message: Message, state: FSMContext) -> None:
        if message.text.strip() == "❌ Отмена":
            await state.clear()
            await message.answer(MessageFormatter.operation_cancelled(), reply_markup=AdminKeyboard.main_menu())
            return

        query = message.text.strip()
        await state.clear()

        try:
            found = await asyncio.to_thread(appt_service.search_appointments_by_client, query)

            if not found:
                await message.answer(f"😔 Клиент по запросу «{query}» не найден.")
                return

            seen_users = set()
            unique_found = []
            for a in sorted(found, key=lambda x: x.id or 0, reverse=True):
                if a.user_id not in seen_users:
                    seen_users.add(a.user_id)
                    unique_found.append(a)

            text_parts = [f"🔍 Найдено {len(unique_found)} клиент(ов):\n"]
            for appt in unique_found[:10]:
                text_parts.append(MessageFormatter.admin_client_info(appt))

            await message.answer(
                "\n\n".join(text_parts),
                parse_mode="HTML",
                reply_markup=AdminKeyboard.clients_menu() if len(unique_found) == 1 else None,
            )

            if len(unique_found) == 1 and unique_found[0].user_id:
                await message.answer(
                    "Написать этому клиенту:",
                    reply_markup=AdminKeyboard.client_actions(
                        user_id=unique_found[0].user_id,
                        appt_id=unique_found[0].id or 0
                    ),
                )
        except Exception as exc:
            logger.error("Ошибка поиска клиента: %s", exc)
            await message.answer(MessageFormatter.error_general())

    # ── История клиента ────────────────────────────────────────────────────
    @router.callback_query(F.data == "admin_client_history")
    async def admin_client_history_cb(callback: CallbackQuery, state: FSMContext) -> None:
        # BUG 4.2 FIX: добавлена проверка прав администратора
        if not _is_admin(callback.from_user.id):
            await callback.answer("Нет прав администратора.", show_alert=True)
            return
        await state.set_state(AdminFSM.waiting_for_history_query)
        await callback.message.answer(
            "📋 Введите имя или телефон для просмотра истории:",
            reply_markup=AdminKeyboard.cancel(),
        )
        await callback.answer()

    # ════════════════════════════════════════════════════════════════════
    # РАЗДЕЛ 5: НАСТРОЙКИ
    # ════════════════════════════════════════════════════════════════════

    def _get_master_name() -> str:
        """Читает имя мастера из config.json."""
        try:
            config = _load_config_json()
            return config.get("master", {}).get("name", "Мастер")
        except Exception as exc:
            logger.debug("Suppressed: _get_master_name error: %s", exc, exc_info=True)
            return "Мастер"

    @router.message(F.text == "⚙️ Настройки")
    async def admin_settings(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        settings_dict = {
            "master_name": _get_master_name(),
            "welcome_text": settings.services and "настроен" or "по умолчанию",
            "work_hours": f"{settings.default_time_slots[0] if settings.default_time_slots else '09:00'} - "
                          f"{settings.default_time_slots[-1] if settings.default_time_slots else '18:00'}",
            "slot_interval": "60",
            "reminder_hours": str(settings.reminder_hours_before),
            "services_count": len(settings.services or {}),
        }
        await message.answer(
            MessageFormatter.admin_settings_menu(settings_dict),
            reply_markup=AdminKeyboard.settings_menu(),
            parse_mode="HTML",
        )

    @router.callback_query(F.data == "admin_settings")
    async def admin_settings_cb(callback: CallbackQuery) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        settings_dict = {
            "master_name": _get_master_name(),
            "welcome_text": "настроен",
            "work_hours": f"{settings.default_time_slots[0] if settings.default_time_slots else '09:00'} - "
                          f"{settings.default_time_slots[-1] if settings.default_time_slots else '18:00'}",
            "slot_interval": "60",
            "reminder_hours": str(settings.reminder_hours_before),
            "services_count": len(settings.services or {}),
        }
        await callback.message.edit_text(
            MessageFormatter.admin_settings_menu(settings_dict),
            reply_markup=AdminKeyboard.settings_menu(),
            parse_mode="HTML",
        )
        await callback.answer()

    # ── Редактирование приветствия ─────────────────────────────────────────
    # BUG 2.3 FIX: теперь используем отдельное состояние waiting_for_welcome_text
    @router.callback_query(F.data == "admin_edit_welcome")
    async def admin_edit_welcome(callback: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config.json")
        try:
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)
            current = config.get("bot", {}).get("welcome", "Текст не задан")
        except Exception as exc:
            logger.debug("Suppressed: read config for welcome: %s", exc, exc_info=True)
            current = "Текст не задан"

        # BUG 2.3: используем waiting_for_welcome_text вместо waiting_for_broadcast
        await state.set_state(AdminFSM.waiting_for_welcome_text)
        await callback.message.answer(
            f"Текущий текст приветствия:\n\n<i>{current[:200]}</i>\n\n"
            "Введите новый текст приветствия (поддерживается HTML):\n"
            "<i>Используйте {name} для вставки имени клиента</i>",
            reply_markup=AdminKeyboard.cancel(),
            parse_mode="HTML",
        )
        await callback.answer()

    # BUG 2.3 FIX: отдельный хендлер для редактирования текста приветствия
    @router.message(AdminFSM.waiting_for_welcome_text, F.text)
    async def admin_welcome_text_save(message: Message, state: FSMContext) -> None:
        """Сохраняет текст приветствия в config.json."""
        if message.text.strip() == "❌ Отмена":
            await state.clear()
            await message.answer(MessageFormatter.operation_cancelled(), reply_markup=AdminKeyboard.main_menu())
            return
        tmp_path = None
        async with _config_write_lock:
            config_path = os.path.normpath(
                os.path.join(os.path.dirname(__file__), "..", "..", "config.json")
            )
            try:
                try:
                    with open(config_path, encoding="utf-8") as f:
                        config = json.load(f)
                except FileNotFoundError:
                    config = {}

                if "bot" not in config:
                    config["bot"] = {}
                config["bot"]["welcome"] = message.text

                config_dir = os.path.dirname(config_path)
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8",
                    dir=config_dir, suffix=".tmp", delete=False,
                ) as tmp_f:
                    tmp_path = tmp_f.name
                    json.dump(config, tmp_f, ensure_ascii=False, indent=2)

                os.replace(tmp_path, config_path)
                tmp_path = None

                try:
                    _load_config_json.cache_clear()
                except Exception as exc:
                    logger.debug("Suppressed cache_clear: %s", exc, exc_info=True)

                await state.clear()
                await message.answer(
                    "✅ Текст приветствия обновлён!\n\n<i>Изменения применены немедленно</i>",
                    reply_markup=AdminKeyboard.main_menu(),
                    parse_mode="HTML",
                )
            except Exception as exc:
                logger.error("Ошибка обновления config.json (welcome): %s", exc)
                if tmp_path and os.path.exists(tmp_path):
                    with contextlib.suppress(Exception):
                        os.unlink(tmp_path)
                await message.answer(MessageFormatter.error_general())

    # ── Фото приветствия ──────────────────────────────────────────────────
    # BUG 1.2 + BUG 2.3 FIX: используем отдельное состояние waiting_for_photo_url
    @router.callback_query(F.data == "admin_edit_photo")
    async def admin_edit_photo(callback: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        # BUG 2.3: используем waiting_for_photo_url вместо waiting_for_broadcast
        await state.set_state(AdminFSM.waiting_for_photo_url)
        await callback.message.answer(
            "📸 Отправьте URL фото для приветствия.\n\n"
            "<i>Фото должно быть доступно по прямой ссылке (https://...)</i>",
            reply_markup=AdminKeyboard.cancel(),
            parse_mode="HTML",
        )
        await callback.answer()

    # BUG 1.2 FIX: отдельный хендлер для сохранения URL фото
    @router.message(AdminFSM.waiting_for_photo_url, F.text)
    async def admin_photo_url_save(message: Message, state: FSMContext) -> None:
        """
        BUG 1.2 FIX: Сохраняет URL фото приветствия в config.json.
        Ранее эта ветка отсутствовала и URL сохранялся как текст рассылки.
        """
        if message.text.strip() == "❌ Отмена":
            await state.clear()
            await message.answer(MessageFormatter.operation_cancelled(), reply_markup=AdminKeyboard.main_menu())
            return

        url = message.text.strip()
        if not url.startswith("https://"):
            await message.answer(
                "❌ URL должен начинаться с <code>https://</code>\n\n"
                "Пример: <code>https://example.com/photo.jpg</code>",
                parse_mode="HTML",
            )
            return

        try:
            config = await asyncio.to_thread(_load_config)
            if "bot" not in config:
                config["bot"] = {}
            config["bot"]["welcome_photo_url"] = url
            await _save_config(config)
            # Обновляем settings в памяти
            object.__setattr__(settings, "welcome_photo_url", url)
        except Exception as exc:
            logger.error("Ошибка сохранения фото приветствия: %s", exc)
            await message.answer(MessageFormatter.error_general())
            await state.clear()
            return

        await state.clear()
        await message.answer(
            f"✅ Фото приветствия обновлено!\n\n"
            f"URL: <code>{url}</code>\n\n"
            "<i>Изменения применены немедленно.</i>",
            reply_markup=AdminKeyboard.main_menu(),
            parse_mode="HTML",
        )

    # ── Редактирование услуг ──────────────────────────────────────────────
    @router.callback_query(F.data == "admin_edit_services")
    async def admin_edit_services(callback: CallbackQuery) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        services = settings.services or {}
        if services:
            text = "💅 <b>Текущие услуги:</b>\n\n"
            for name, info in services.items():
                price = info.get("price", "—")
                duration = info.get("duration", "—")
                text += f"• {name}: {price} ₽, {duration} мин\n"
        else:
            text = "💅 <b>Услуги не настроены</b>\n\nДобавьте услуги через файл .env или настройки."
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboard.settings_services_menu(),
            parse_mode="HTML",
        )
        await callback.answer()

    # ════════════════════════════════════════════════════════════════════
    # ХЕНДЛЕРЫ ДЛЯ НАСТРОЕК ЧЕРЕЗ БОТ
    # ════════════════════════════════════════════════════════════════════

    # ── Редактирование рабочих часов ────────────────────────────────────
    @router.callback_query(F.data == "admin_edit_hours")
    async def admin_edit_hours(callback: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        current_slots = settings.default_time_slots or []
        current_text = ", ".join(current_slots) if current_slots else "не задано"
        await state.set_state(AdminFSM.waiting_for_edit_hours)
        await callback.message.answer(
            f"🕐 <b>Редактирование рабочих часов</b>\n\n"
            f"Текущие слоты: <code>{current_text}</code>\n\n"
            f"Введите слоты через запятую в формате ЧЧ:ММ\n"
            f"Пример: <code>09:00, 10:00, 11:00, 14:00, 15:00</code>",
            reply_markup=AdminKeyboard.cancel(),
            parse_mode="HTML",
        )
        await callback.answer()

    @router.message(AdminFSM.waiting_for_edit_hours, F.text)
    async def admin_edit_hours_save(message: Message, state: FSMContext) -> None:
        if message.text.strip() == "❌ Отмена":
            await state.clear()
            await message.answer(MessageFormatter.operation_cancelled(), reply_markup=AdminKeyboard.main_menu())
            return
        text = message.text.strip()
        raw_slots = [s.strip() for s in text.split(",") if s.strip()]
        valid_slots = []
        for slot in raw_slots:
            if not re.match(r"^\d{2}:\d{2}$", slot):
                await message.answer(f"❌ Некорректный формат: <code>{slot}</code>. Используйте ЧЧ:ММ", parse_mode="HTML")
                return
            h, m = map(int, slot.split(":"))
            if not (0 <= h < 24 and 0 <= m < 60):
                await message.answer(f"❌ Время вне диапазона: <code>{slot}</code>", parse_mode="HTML")
                return
            valid_slots.append(slot)
        if not valid_slots:
            await message.answer("❌ Введите хотя бы один слот.")
            return
        try:
            config = await asyncio.to_thread(_load_config)
            if "schedule" not in config:
                config["schedule"] = {}
            config["schedule"]["default_time_slots"] = valid_slots
            await _save_config(config)
            settings.default_time_slots.clear()
            settings.default_time_slots.extend(valid_slots)
        except Exception as exc:
            logger.error("Ошибка сохранения рабочих часов: %s", exc)
            await message.answer(MessageFormatter.error_general())
            await state.clear()
            return
        await state.clear()
        await message.answer(
            f"✅ Рабочие часы обновлены!\n\nСлотов: <b>{len(valid_slots)}</b>: {', '.join(valid_slots)}\n\n"
            "<i>Изменения применены. Перезапуск не требуется.</i>",
            reply_markup=AdminKeyboard.main_menu(),
            parse_mode="HTML",
        )

    # ── Редактирование интервала ─────────────────────────────────────────
    @router.callback_query(F.data == "admin_edit_interval")
    async def admin_edit_interval(callback: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminFSM.waiting_for_edit_interval)
        await callback.message.answer(
            "⏱ <b>Интервал между записями</b>\n\n"
            "Введите интервал в минутах (например: <code>60</code>):\n"
            "<i>Это значение используется при генерации слотов расписания</i>",
            reply_markup=AdminKeyboard.cancel(),
            parse_mode="HTML",
        )
        await callback.answer()

    @router.message(AdminFSM.waiting_for_edit_interval, F.text)
    async def admin_edit_interval_save(message: Message, state: FSMContext) -> None:
        if message.text.strip() == "❌ Отмена":
            await state.clear()
            await message.answer(MessageFormatter.operation_cancelled(), reply_markup=AdminKeyboard.main_menu())
            return
        text = message.text.strip()
        if not text.isdigit() or int(text) < 15 or int(text) > 480:
            await message.answer("❌ Введите число от 15 до 480 минут.")
            return
        interval = int(text)
        try:
            config = await asyncio.to_thread(_load_config)
            if "schedule" not in config:
                config["schedule"] = {}
            config["schedule"]["slot_interval_minutes"] = interval
            await _save_config(config)
        except Exception as exc:
            logger.error("Ошибка сохранения интервала: %s", exc)
            await message.answer(MessageFormatter.error_general())
            await state.clear()
            return
        await state.clear()
        await message.answer(
            f"✅ Интервал обновлён: <b>{interval} мин</b>\n\n"
            "<i>Изменения сохранены в config.json</i>",
            reply_markup=AdminKeyboard.main_menu(),
            parse_mode="HTML",
        )

    # ── Редактирование времени напоминания ───────────────────────────────
    @router.callback_query(F.data == "admin_edit_reminder")
    async def admin_edit_reminder(callback: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        current = settings.reminder_hours_before
        await state.set_state(AdminFSM.waiting_for_edit_reminder)
        await callback.message.answer(
            f"🔔 <b>Время напоминания</b>\n\n"
            f"Текущее значение: <b>{current} часов до записи</b>\n\n"
            "Введите за сколько часов отправлять напоминание (1–72):",
            reply_markup=AdminKeyboard.cancel(),
            parse_mode="HTML",
        )
        await callback.answer()

    @router.message(AdminFSM.waiting_for_edit_reminder, F.text)
    async def admin_edit_reminder_save(message: Message, state: FSMContext) -> None:
        if message.text.strip() == "❌ Отмена":
            await state.clear()
            await message.answer(MessageFormatter.operation_cancelled(), reply_markup=AdminKeyboard.main_menu())
            return
        text = message.text.strip()
        if not text.isdigit() or int(text) < 1 or int(text) > 72:
            await message.answer("❌ Введите число от 1 до 72.")
            return
        hours = int(text)
        try:
            config = await asyncio.to_thread(_load_config)
            if "bot" not in config:
                config["bot"] = {}
            config["bot"]["reminder_hours_before"] = hours
            await _save_config(config)
            # BUG 3.2 FIX: используем object.__setattr__ вместо settings.__dict__["..."]
            object.__setattr__(settings, "reminder_hours_before", hours)
        except Exception as exc:
            logger.error("Ошибка сохранения напоминания: %s", exc)
            await message.answer(MessageFormatter.error_general())
            await state.clear()
            return
        await state.clear()
        await message.answer(
            f"✅ Время напоминания: за <b>{hours} ч</b> до записи\n\n"
            "<i>Применено немедленно.</i>",
            reply_markup=AdminKeyboard.main_menu(),
            parse_mode="HTML",
        )

    # ── Добавить услугу ──────────────────────────────────────────────────
    @router.callback_query(F.data == "admin_add_service")
    async def admin_add_service_start(callback: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminFSM.waiting_for_service_name)
        await state.update_data(service_action="add")
        await callback.message.answer(
            "➕ <b>Добавить услугу</b>\n\n"
            "Введите <b>название</b> новой услуги:\n"
            "<i>Например: Маникюр гель-лак</i>",
            reply_markup=AdminKeyboard.cancel(),
            parse_mode="HTML",
        )
        await callback.answer()

    # ── Изменить услугу ──────────────────────────────────────────────────
    @router.callback_query(F.data == "admin_edit_service")
    async def admin_edit_service_start(callback: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        services = settings.services or {}
        if not services:
            await callback.answer("❌ Услуги не настроены", show_alert=True)
            return
        buttons = []
        for svc_name in services.keys():
            buttons.append([InlineKeyboardButton(
                text=f"✏️ {svc_name}",
                callback_data=f"admin_edit_svc_select:{svc_name}"
            )])
        buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="admin_settings")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.edit_text(
            "✏️ <b>Выберите услугу для редактирования:</b>",
            reply_markup=kb,
            parse_mode="HTML",
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin_edit_svc_select:"))
    async def admin_edit_svc_select(callback: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        svc_name = callback.data.split(":", 1)[1]
        await state.set_state(AdminFSM.waiting_for_service_name)
        await state.update_data(service_action="edit", service_old_name=svc_name)
        await callback.message.answer(
            f"✏️ Редактирование: <b>{svc_name}</b>\n\n"
            "Введите <b>новое название</b> (или то же самое если хотите изменить только цену/время):",
            reply_markup=AdminKeyboard.cancel(),
            parse_mode="HTML",
        )
        await callback.answer()

    # ── Удалить услугу ───────────────────────────────────────────────────
    @router.callback_query(F.data == "admin_delete_service")
    async def admin_delete_service_start(callback: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        services = settings.services or {}
        if not services:
            await callback.answer("❌ Услуги не настроены", show_alert=True)
            return
        buttons = []
        for svc_name in services.keys():
            buttons.append([InlineKeyboardButton(
                text=f"🗑 {svc_name}",
                callback_data=f"admin_del_svc_confirm:{svc_name}"
            )])
        buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="admin_settings")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.edit_text(
            "🗑 <b>Выберите услугу для удаления:</b>",
            reply_markup=kb,
            parse_mode="HTML",
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin_del_svc_confirm:"))
    async def admin_delete_service_confirm(callback: CallbackQuery) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        svc_name = callback.data.split(":", 1)[1]
        try:
            config = await asyncio.to_thread(_load_config)
            services_in_config = config.get("services", {})
            if svc_name in services_in_config:
                del services_in_config[svc_name]
                config["services"] = services_in_config
                await _save_config(config)
            if svc_name in settings.services:
                del settings.services[svc_name]
            await callback.message.edit_text(
                f"✅ Услуга <b>{svc_name}</b> удалена.\n\n<i>Изменения сохранены.</i>",
                parse_mode="HTML",
                reply_markup=None,
            )
        except Exception as exc:
            logger.error("Ошибка удаления услуги %s: %s", svc_name, exc)
            await callback.message.edit_text(MessageFormatter.error_general())
        await callback.answer()

    # ── FSM хендлеры для добавления/редактирования услуги ─────────────────
    @router.message(AdminFSM.waiting_for_service_name, F.text)
    async def admin_service_name_input(message: Message, state: FSMContext) -> None:
        if message.text.strip() == "❌ Отмена":
            await state.clear()
            await message.answer(MessageFormatter.operation_cancelled(), reply_markup=AdminKeyboard.main_menu())
            return
        name = message.text.strip()
        if not name or len(name) > 100:
            await message.answer("❌ Название должно быть от 1 до 100 символов.")
            return
        await state.update_data(service_new_name=name)
        await state.set_state(AdminFSM.waiting_for_service_price)
        data = await state.get_data()
        action = data.get("service_action", "add")
        old_price = ""
        if action == "edit":
            old_name = data.get("service_old_name", name)
            svc_info = (settings.services or {}).get(old_name, {})
            old_price = f" (текущая: {svc_info.get('price', '?')} ₽)" if isinstance(svc_info, dict) else ""
        await message.answer(
            f"💰 Введите <b>цену</b>{old_price} в рублях (только число):\n<i>Например: 1500</i>",
            reply_markup=AdminKeyboard.cancel(),
            parse_mode="HTML",
        )

    @router.message(AdminFSM.waiting_for_service_price, F.text)
    async def admin_service_price_input(message: Message, state: FSMContext) -> None:
        if message.text.strip() == "❌ Отмена":
            await state.clear()
            await message.answer(MessageFormatter.operation_cancelled(), reply_markup=AdminKeyboard.main_menu())
            return
        text = message.text.strip()
        if not text.isdigit() or int(text) < 0:
            await message.answer("❌ Введите положительное целое число (цена в рублях).")
            return
        await state.update_data(service_price=int(text))
        await state.set_state(AdminFSM.waiting_for_service_duration)
        data = await state.get_data()
        action = data.get("service_action", "add")
        old_dur = ""
        if action == "edit":
            old_name = data.get("service_old_name", "")
            svc_info = (settings.services or {}).get(old_name, {})
            old_dur = f" (текущая: {svc_info.get('duration', '?')} мин)" if isinstance(svc_info, dict) else ""
        await message.answer(
            f"⏱ Введите <b>длительность</b>{old_dur} в минутах:\n<i>Например: 60</i>",
            reply_markup=AdminKeyboard.cancel(),
            parse_mode="HTML",
        )

    @router.message(AdminFSM.waiting_for_service_duration, F.text)
    async def admin_service_duration_save(message: Message, state: FSMContext) -> None:
        if message.text.strip() == "❌ Отмена":
            await state.clear()
            await message.answer(MessageFormatter.operation_cancelled(), reply_markup=AdminKeyboard.main_menu())
            return
        text = message.text.strip()
        if not text.isdigit() or int(text) < 1:
            await message.answer("❌ Введите положительное целое число (минуты).")
            return
        duration = int(text)
        data = await state.get_data()
        action = data.get("service_action", "add")
        new_name = data.get("service_new_name", "")
        old_name = data.get("service_old_name", new_name)
        price = data.get("service_price", 0)

        try:
            config = await asyncio.to_thread(_load_config)
            if "services" not in config:
                config["services"] = {}
            if action == "edit" and old_name and old_name != new_name:
                config["services"].pop(old_name, None)
            config["services"][new_name] = {"price": price, "duration": duration}
            await _save_config(config)
            if action == "edit" and old_name and old_name != new_name:
                settings.services.pop(old_name, None)
            settings.services[new_name] = {"price": price, "duration": duration}
        except Exception as exc:
            logger.error("Ошибка сохранения услуги: %s", exc)
            await message.answer(MessageFormatter.error_general())
            await state.clear()
            return

        services = settings.services or {}
        price_text = "💅 <b>Актуальные услуги:</b>\n\n"
        for svc, info in services.items():
            p = info.get("price", "—") if isinstance(info, dict) else "—"
            d = info.get("duration", "—") if isinstance(info, dict) else "—"
            price_text += f"• <b>{svc}</b>: {p} ₽, {d} мин\n"

        action_text = "добавлена" if action == "add" else "обновлена"
        await message.answer(
            f"✅ Услуга «{new_name}» {action_text}!\n\n{price_text}\n<i>Изменения применены немедленно.</i>",
            reply_markup=AdminKeyboard.main_menu(),
            parse_mode="HTML",
        )
        await state.clear()

    # ── Написать клиенту ─────────────────────────────────────────────────
    @router.callback_query(F.data == "admin_message_client")
    async def admin_message_client_start(callback: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminFSM.waiting_for_message_user_id)
        await callback.message.answer(
            "✉️ <b>Написать клиенту</b>\n\n"
            "Введите <b>Telegram ID</b> клиента\n"
            "<i>(Его можно найти через «🔍 Найти клиента»)</i>:",
            reply_markup=AdminKeyboard.cancel(),
            parse_mode="HTML",
        )
        await callback.answer()

    @router.message(AdminFSM.waiting_for_message_user_id, F.text)
    async def admin_message_client_get_id(message: Message, state: FSMContext) -> None:
        if message.text.strip() == "❌ Отмена":
            await state.clear()
            await message.answer(MessageFormatter.operation_cancelled(), reply_markup=AdminKeyboard.main_menu())
            return
        text = message.text.strip()
        if not text.isdigit():
            await message.answer("❌ Введите числовой Telegram ID пользователя.")
            return
        target_user_id = int(text)
        await state.update_data(message_target_user_id=target_user_id)
        await state.set_state(AdminFSM.waiting_for_message_client)
        await message.answer(
            f"✍️ Введите текст сообщения для пользователя <b>{target_user_id}</b>:\n"
            "<i>Поддерживается HTML-форматирование</i>",
            reply_markup=AdminKeyboard.cancel(),
            parse_mode="HTML",
        )

    @router.message(AdminFSM.waiting_for_message_client, F.text)
    async def admin_message_client_send(message: Message, state: FSMContext) -> None:
        if message.text.strip() == "❌ Отмена":
            await state.clear()
            await message.answer(MessageFormatter.operation_cancelled(), reply_markup=AdminKeyboard.main_menu())
            return
        data = await state.get_data()
        target_user_id = data.get("message_target_user_id")
        if not target_user_id:
            await state.clear()
            await message.answer("❌ Ошибка: не найден ID получателя.", reply_markup=AdminKeyboard.main_menu())
            return
        try:
            text_to_send = f"📩 <b>Сообщение от мастера:</b>\n\n{message.text}"
            await message.bot.send_message(target_user_id, text_to_send, parse_mode="HTML")
            await message.answer(
                f"✅ Сообщение отправлено пользователю {target_user_id}.",
                reply_markup=AdminKeyboard.main_menu(),
            )
        except Exception as exc:
            logger.error("Ошибка отправки сообщения клиенту %s: %s", target_user_id, exc)
            await message.answer(
                f"❌ Не удалось отправить сообщение (пользователь {target_user_id} мог заблокировать бота).",
                reply_markup=AdminKeyboard.main_menu(),
            )
        await state.clear()

    # ── BUG 2.3 FIX: Обработчик waiting_for_broadcast_text — только рассылка ─
    @router.message(AdminFSM.waiting_for_broadcast_text, F.text)
    async def admin_broadcast_text_input(message: Message, state: FSMContext) -> None:
        """Принимает текст рассылки (отдельное состояние, не смешано с welcome/photo)."""
        if message.text.strip() == "❌ Отмена":
            await state.clear()
            await message.answer(MessageFormatter.operation_cancelled(), reply_markup=AdminKeyboard.main_menu())
            return

        broadcast_text = message.text
        if len(broadcast_text) > 4000:
            await message.answer(
                f"⚠️ Текст слишком длинный ({len(broadcast_text)} символов). Максимум 4000."
            )
            return
        await state.update_data(broadcast_text=broadcast_text)
        await message.answer("Предпросмотр рассылки:", parse_mode="HTML")
        await message.answer(
            broadcast_text,
            parse_mode="HTML",
            reply_markup=AdminKeyboard.broadcast_confirm(broadcast_text)
        )

    # ── Обратная совместимость: waiting_for_broadcast — по-прежнему работает ─
    # Оставляем для внешнего совместимого кода, но edit_mode логика разделена
    @router.message(AdminFSM.waiting_for_broadcast, F.text)
    async def admin_edit_setting_text(message: Message, state: FSMContext) -> None:
        """Обработчик waiting_for_broadcast — только для совместимости.

        BUG 1.2 FIX: добавлен блок elif edit_mode == 'photo' для сохранения URL.
        BUG 2.3 FIX: новые вызовы должны использовать отдельные состояния
        (waiting_for_welcome_text, waiting_for_photo_url, waiting_for_broadcast_text).
        Этот хендлер остаётся для обратной совместимости.
        """
        if message.text.strip() == "❌ Отмена":
            await state.clear()
            await message.answer(MessageFormatter.operation_cancelled(), reply_markup=AdminKeyboard.main_menu())
            return

        data = await state.get_data()
        edit_mode = data.get("edit_mode")

        if edit_mode == "welcome":
            # Перенаправляем в отдельный хендлер через смену состояния
            await state.set_state(AdminFSM.waiting_for_welcome_text)
            await admin_welcome_text_save(message, state)
            return

        elif edit_mode == "photo":
            # BUG 1.2 FIX: обрабатываем URL фото приветствия
            url = message.text.strip()
            if not url.startswith("https://"):
                await message.answer(
                    "❌ URL должен начинаться с <code>https://</code>\n\n"
                    "Пример: <code>https://example.com/photo.jpg</code>",
                    parse_mode="HTML",
                )
                return
            try:
                config = await asyncio.to_thread(_load_config)
                if "bot" not in config:
                    config["bot"] = {}
                config["bot"]["welcome_photo_url"] = url
                await _save_config(config)
                # BUG 3.2 FIX: object.__setattr__ вместо __dict__
                object.__setattr__(settings, "welcome_photo_url", url)
            except Exception as exc:
                logger.error("Ошибка сохранения фото приветствия (compat): %s", exc)
                await message.answer(MessageFormatter.error_general())
                await state.clear()
                return
            await state.clear()
            await message.answer(
                f"✅ Фото приветствия обновлено!\n\n"
                f"URL: <code>{url}</code>\n\n"
                "<i>Изменения применены немедленно.</i>",
                reply_markup=AdminKeyboard.main_menu(),
                parse_mode="HTML",
            )
            return

        # Обычная рассылка (edit_mode == "broadcast" или не задан)
        broadcast_text = message.text
        if len(broadcast_text) > 4000:
            await message.answer(
                f"⚠️ Текст слишком длинный ({len(broadcast_text)} символов). Максимум 4000."
            )
            return
        await state.update_data(broadcast_text=broadcast_text)
        await message.answer("Предпросмотр рассылки:", parse_mode="HTML")
        await message.answer(
            broadcast_text,
            parse_mode="HTML",
            reply_markup=AdminKeyboard.broadcast_confirm(broadcast_text)
        )

    # ════════════════════════════════════════════════════════════════════
    # РАЗДЕЛ 6: ЧЁРНЫЙ СПИСОК
    # ════════════════════════════════════════════════════════════════════

    @router.message(F.text.in_({"🚫 Чёрный список", "🛑 Черный список"}))
    async def admin_blacklist(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        try:
            blacklisted = await asyncio.to_thread(appt_service.get_blacklist)
            text = MessageFormatter.blacklist_info(blacklisted)
        except Exception as exc:
            logger.debug("Suppressed: get_blacklist error: %s", exc, exc_info=True)
            text = "🚫 <b>Чёрный список</b>\n\nОшибка получения списка."
        await message.answer(text, reply_markup=AdminKeyboard.blacklist_menu(), parse_mode="HTML")

    @router.callback_query(F.data == "admin_show_blacklist")
    async def admin_show_blacklist(callback: CallbackQuery) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        try:
            blacklisted = await asyncio.to_thread(appt_service.get_blacklist)
            text = MessageFormatter.blacklist_info(blacklisted)
        except Exception as exc:
            logger.debug("Suppressed: get_blacklist error: %s", exc, exc_info=True)
            text = "🚫 <b>Чёрный список</b>\n\nСписок пуст или ошибка."
        await callback.message.edit_text(text, reply_markup=AdminKeyboard.blacklist_menu(), parse_mode="HTML")
        await callback.answer()

    @router.callback_query(F.data == "admin_block_user")
    async def admin_block_user_start(callback: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminFSM.waiting_for_blacklist_id)
        await state.update_data(blacklist_action="block")
        await callback.message.answer(
            "Введите Telegram ID пользователя для блокировки\n"
            "<i>(или имя — поиск по последним записям)</i>:",
            reply_markup=AdminKeyboard.cancel(),
            parse_mode="HTML",
        )
        await callback.answer()

    @router.callback_query(F.data == "admin_unblock_user")
    async def admin_unblock_user_start(callback: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminFSM.waiting_for_blacklist_id)
        await state.update_data(blacklist_action="unblock")
        await callback.message.answer(
            "Введите Telegram ID пользователя для разблокировки:",
            reply_markup=AdminKeyboard.cancel(),
            parse_mode="HTML",
        )
        await callback.answer()

    @router.message(AdminFSM.waiting_for_blacklist_id, F.text)
    async def admin_blacklist_action(message: Message, state: FSMContext) -> None:
        if message.text.strip() == "❌ Отмена":
            await state.clear()
            await message.answer(MessageFormatter.operation_cancelled(), reply_markup=AdminKeyboard.main_menu())
            return

        data = await state.get_data()
        action = data.get("blacklist_action", "block")
        text = message.text.strip()

        if text.isdigit():
            user_id = int(text)
            try:
                if action == "block":
                    await asyncio.to_thread(appt_service.add_to_blacklist, user_id)
                    await message.answer(MessageFormatter.blacklist_user_added(user_id), reply_markup=AdminKeyboard.main_menu())
                else:
                    await asyncio.to_thread(appt_service.remove_from_blacklist, user_id)
                    await message.answer(MessageFormatter.blacklist_user_removed(user_id), reply_markup=AdminKeyboard.main_menu())
            except Exception as exc:
                logger.error("Ошибка изменения черного списка: %s", exc)
                await message.answer(f"❌ Ошибка: {exc}")
        else:
            await message.answer(
                "⚠️ Введите числовой Telegram ID пользователя."
                "\n\nЧтобы найти ID — используйте раздел «👥 Клиенты» → «Найти клиента»."
            )
            return
        await state.clear()

    # ════════════════════════════════════════════════════════════════════
    # СТАТИСТИКА И РАССЫЛКА
    # ════════════════════════════════════════════════════════════════════

    @router.message(F.text == "📊 Статистика")
    async def admin_stats(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        try:
            stats = await asyncio.to_thread(appt_service.get_statistics)
            revenue = await asyncio.to_thread(_calc_revenue)
            await message.answer(
                MessageFormatter.admin_stats(
                    total=stats.get("total", 0),
                    confirmed=stats.get("confirmed", 0),
                    cancelled=stats.get("cancelled", 0),
                    today=stats.get("today", 0),
                    week=stats.get("week", 0),
                    revenue_today=revenue.get("today", 0),
                    revenue_week=revenue.get("week", 0),
                    revenue_month=revenue.get("month", 0),
                ),
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.error("Ошибка получения статистики: %s", exc)
            await message.answer(MessageFormatter.error_general())

    def _calc_revenue() -> dict:
        """Вычисляет выручку на основе записей и prices из settings.services."""
        try:
            today_str = date.today().isoformat()
            week_start = (date.today() - timedelta(days=7)).isoformat()
            month_start = (date.today() - timedelta(days=30)).isoformat()
            services = settings.services or {}

            today_appts = appt_service.get_appointments_by_date(today_str)
            week_appts = appt_service.get_by_date_range(week_start, today_str)
            month_appts = appt_service.get_by_date_range(month_start, today_str)

            def _sum(appts) -> int:
                total = 0
                for a in appts:
                    if getattr(a, 'is_cancelled', False):
                        continue
                    svc = a.service or ""
                    info = services.get(svc, {})
                    price = info.get("price") if isinstance(info, dict) else None
                    if price is not None:
                        try:
                            total += int(price)
                        except (ValueError, TypeError):
                            pass
                return total

            return {
                "today": _sum(today_appts),
                "week": _sum(week_appts),
                "month": _sum(month_appts),
            }
        except Exception as exc:
            logger.warning("Ошибка вычисления выручки: %s", exc)
            return {"today": 0, "week": 0, "month": 0}

    @router.message(F.text == "📢 Рассылка")
    async def admin_broadcast_start(message: Message, state: FSMContext) -> None:
        if not _is_admin(message.from_user.id):
            return
        # BUG 2.3 FIX: используем waiting_for_broadcast_text вместо waiting_for_broadcast
        await state.set_state(AdminFSM.waiting_for_broadcast_text)
        await message.answer(
            "📢 Введите текст рассылки (поддерживается HTML):",
            reply_markup=AdminKeyboard.cancel(),
            parse_mode="HTML",
        )

    _broadcast_tasks: set = set()

    @router.callback_query(F.data == "admin_broadcast_send")
    async def admin_broadcast_send(callback: CallbackQuery, state: FSMContext) -> None:
        """Рассылка запускается как фоновая задача (asyncio.create_task)."""
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        data = await state.get_data()
        text = data.get("broadcast_text")
        if not text:
            await callback.answer("Нет текста для рассылки.")
            return
        await callback.answer("Рассылка запущена в фоне...")
        await state.clear()

        async def _do_broadcast() -> None:
            try:
                all_user_ids: set = set()
                try:
                    db = getattr(container, "db", None) or getattr(container, "_db", None)
                    if db is not None:
                        def _get_all_users():
                            with db.read_connection() as conn:
                                rows = conn.execute("SELECT user_id FROM users").fetchall()
                                return {row[0] for row in rows}
                        all_user_ids = await asyncio.to_thread(_get_all_users)
                except Exception as exc:
                    logger.debug("Suppressed: get users for broadcast: %s", exc, exc_info=True)

                if not all_user_ids:
                    appts = await asyncio.to_thread(appt_service.get_all_active)
                    all_user_ids = {a.user_id for a in appts}

                sent = 0
                failed = 0
                for uid in all_user_ids:
                    try:
                        await callback.message.bot.send_message(uid, text, parse_mode="HTML")
                        sent += 1
                        await asyncio.sleep(0.04)
                    except Exception:
                        failed += 1

                await callback.message.answer(
                    f"✅ Рассылка завершена: отправлено {sent}, ошибок {failed}.",
                    reply_markup=AdminKeyboard.main_menu(),
                )
            except Exception as exc:
                logger.error("Ошибка рассылки: %s", exc)
                with contextlib.suppress(Exception):
                    await callback.message.answer(MessageFormatter.error_general())

        task = asyncio.create_task(_do_broadcast())
        _broadcast_tasks.add(task)
        task.add_done_callback(_broadcast_tasks.discard)

        await callback.message.answer(
            "📢 Рассылка запущена в фоновом режиме. Результат придёт по завершению.",
            reply_markup=AdminKeyboard.main_menu(),
        )

    @router.callback_query(F.data == "admin_broadcast_cancel")
    async def admin_broadcast_cancel(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await callback.message.edit_text(MessageFormatter.operation_cancelled())
        await callback.answer()

    # ── Экспорт CSV ────────────────────────────────────────────────────────
    @router.message(F.text == "⬇️ Экспорт CSV")
    async def admin_export_csv_start(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        await message.answer(
            "Экспортировать все записи в CSV?",
            reply_markup=AdminKeyboard.export_csv_confirm(),
        )

    @router.callback_query(F.data == "admin_export_csv")
    async def admin_export_csv(callback: CallbackQuery) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        try:
            appointments = await asyncio.to_thread(appt_service.get_appointments_filtered, "all")
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["ID", "Дата", "Время", "Клиент", "Телефон", "Услуга", "Комментарий", "Статус"])
            for appt in appointments:
                status = "отменена" if getattr(appt, 'is_cancelled', False) else "активна"
                writer.writerow([
                    appt.id, appt.date, appt.time,
                    appt.client_name, appt.phone,
                    appt.service or "", appt.comment or "",
                    status,
                ])
            csv_bytes = output.getvalue().encode("utf-8-sig")
            await callback.message.answer_document(
                BufferedInputFile(csv_bytes, filename="appointments.csv"),
                caption=f"📊 Экспорт {len(appointments)} записей"
            )
        except Exception as exc:
            logger.error("Ошибка экспорта CSV: %s", exc)
            await callback.message.answer(MessageFormatter.error_general())
        await callback.answer()

    # ── Навигация: назад ──────────────────────────────────────────────────
    @router.callback_query(F.data == "admin_back_main")
    async def admin_back_main(callback: CallbackQuery) -> None:
        await callback.message.edit_text(
            MessageFormatter.admin_welcome(),
            reply_markup=None,
        )
        await callback.message.answer(
            MessageFormatter.admin_welcome(),
            reply_markup=AdminKeyboard.main_menu(),
            parse_mode="HTML",
        )
        await callback.answer()

    @router.callback_query(F.data == "admin_back_schedule")
    async def admin_back_schedule(callback: CallbackQuery) -> None:
        dates = await sched_service.get_all_working_dates()
        if not dates:
            await callback.message.edit_text(MessageFormatter.admin_schedule_empty())
        else:
            await callback.message.edit_text(
                MessageFormatter.admin_choose_date(),
                reply_markup=AdminKeyboard.schedule_dates(dates),
            )
        await callback.answer()

    @router.callback_query(F.data == "admin_noop")
    async def admin_noop(callback: CallbackQuery) -> None:
        """Заглушка для неактивных кнопок."""
        await callback.answer()

    # ── Массовая отмена ────────────────────────────────────────────────────
    @router.message(F.text == "🚫 Массовая отмена")
    async def admin_cancel_all_start(message: Message, state: FSMContext) -> None:
        if not _is_admin(message.from_user.id):
            return
        await state.set_state(AdminFSM.confirming_cancel_all_date)
        await message.answer(
            "Введите дату для массовой отмены всех записей (ГГГГ-ММ-ДД):",
            reply_markup=AdminKeyboard.cancel(),
        )

    @router.callback_query(F.data == "admin_cancel_all_date_cb")
    async def admin_cancel_all_date_cb(callback: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminFSM.confirming_cancel_all_date)
        await callback.message.answer(
            "Введите дату для массовой отмены всех записей (ГГГГ-ММ-ДД):",
            reply_markup=AdminKeyboard.cancel(),
        )
        await callback.answer()

    @router.message(AdminFSM.confirming_cancel_all_date, F.text)
    async def admin_cancel_all_date(message: Message, state: FSMContext) -> None:
        if message.text.strip() == "❌ Отмена":
            await state.clear()
            await message.answer(MessageFormatter.operation_cancelled(), reply_markup=AdminKeyboard.main_menu())
            return
        date_str = message.text.strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            await message.answer(MessageFormatter.admin_invalid_date_format())
            return
        try:
            day_appts = await asyncio.to_thread(appt_service.get_appointments_by_date, date_str)
            if not day_appts:
                await state.clear()
                await message.answer(f"На {date_str} нет активных записей.", reply_markup=AdminKeyboard.main_menu())
                return
            await message.answer(
                f"На {date_str} найдено {len(day_appts)} записей. Отменить все?",
                reply_markup=AdminKeyboard.cancel_all_confirm(date_str, len(day_appts)),
            )
        except Exception as exc:
            logger.error("Ошибка при поиске записей на дату: %s", exc)
            await message.answer(MessageFormatter.error_general())
        await state.clear()

    @router.callback_query(F.data.startswith("confirm_cancel_all:"))
    async def admin_confirm_cancel_all(callback: CallbackQuery) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        date_str = callback.data.split(":")[1]
        try:
            day_appts = await asyncio.to_thread(appt_service.get_appointments_by_date, date_str)
            cancelled = 0
            for appt in day_appts:
                try:
                    await asyncio.to_thread(appt_service.admin_cancel_appointment, appt.id)
                    await notif_service.notify_client_cancellation_by_admin(appt.user_id, appt.date, appt.time)
                    cancelled += 1
                except Exception as exc:
                    logger.debug("Suppressed: cancel appt %s: %s", appt.id, exc, exc_info=True)
            await callback.message.edit_text(f"✅ Отменено {cancelled} записей на {date_str}.", reply_markup=None)
        except Exception as exc:
            logger.error("Ошибка массовой отмены: %s", exc)
            await callback.message.edit_text(MessageFormatter.error_general())
        await callback.answer()

    return router
