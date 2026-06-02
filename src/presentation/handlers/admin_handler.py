"""
src/presentation/handlers/admin_handler.py — Административная панель.

Обновлено: 6 разделов (Сегодня, Все записи, Расписание, Клиенты, Настройки, Чёрный список),
кнопки «Пришла» и «Отменить», управление услугами через бот без правки кода,
поиск клиентов, уведомление за 2 часа до первой записи.
"""

import logging
import re
import asyncio
import json
import os

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, BufferedInputFile

from src.config.dependencies import Container
from src.domain.exceptions.appointment import (
    AppointmentNotFoundError,
    AppointmentAlreadyCancelledError,
)
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

    # FIXED HIGH-03: asyncio.Lock для защиты от concurrent записи config.json
    _config_write_lock = asyncio.Lock()

    def _is_admin(user_id: int) -> bool:
        return user_id in settings.admin_ids

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
        except Exception:
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
                await message.answer(
                    f"🕐 <b>{appt.time}</b> — {appt.client_name}",
                    reply_markup=AdminKeyboard.today_appointment_actions(
                        appointment_id=appt.id,
                        client_name=appt.client_name
                    ),
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
                # Пытаемся отметить как выполненную (если метод есть)
                try:
                    await asyncio.to_thread(appt_service.mark_completed, appt_id)
                except AttributeError:
                    pass  # Метод не реализован — просто уведомляем
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
            PAGE_SIZE = 20
            page_appts = appointments[:PAGE_SIZE]
            total = len(appointments)
            filter_label = filter_names.get(filter_key, filter_key)
            text = MessageFormatter.admin_appointments_list(page_appts, filter_name=filter_label)
            if total > PAGE_SIZE:
                text += f"\n\n<i>Показано {PAGE_SIZE} из {total} записей.</i>"
            try:
                await callback.message.edit_text(text, parse_mode="HTML")
            except Exception:
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
            try:
                await state.clear()
            except Exception:
                pass
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

    # ── Добавить слот (из меню) ────────────────────────────────────────────
    @router.callback_query(F.data == "admin_add_slot_manual")
    async def admin_add_slot_start_cb(callback: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminFSM.waiting_for_date)
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
            await message.answer(MessageFormatter.operation_cancelled(), reply_markup=AdminKeyboard.main_menu())
            return

        text = message.text.strip()
        if not re.match(r"^\d{4}[-.]\d{2}[-.]\d{2}$", text) and not re.match(r"^\d{4}-\d{2}-\d{2}$", text):
            await message.answer(MessageFormatter.admin_invalid_date_format())
            return

        date_str = text.replace('.', '-')

        data = await state.get_data()
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
        # FIXED HIGH-04: проверяем реальную корректность значений (regex пропускает 25:99)
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
        await state.set_state(AdminFSM.waiting_for_date)
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
        await state.set_state(AdminFSM.waiting_for_date)
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
        await state.set_state(AdminFSM.waiting_for_date)
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
            from datetime import date, timedelta
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
            appointments = await asyncio.to_thread(appt_service.get_appointments_filtered, "all")
            # Ищем по имени или телефону
            query_lower = query.lower()
            found = [
                a for a in appointments
                if query_lower in (a.client_name or "").lower()
                or query in (a.phone or "")
                or query_lower in (getattr(a, 'username', '') or "").lower()
            ]

            if not found:
                await message.answer(f"😔 Клиент по запросу «{query}» не найден.")
                return

            # Дедупликация по user_id — показываем последнюю запись
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

            # Кнопка «Написать» для одного результата
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
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminFSM.waiting_for_history_query)
        await callback.message.answer(
            "📋 Введите имя или телефон для просмотра истории:",
            reply_markup=AdminKeyboard.cancel(),
        )
        await callback.answer()

    @router.message(AdminFSM.waiting_for_history_query, F.text)
    async def admin_client_history_search(message: Message, state: FSMContext) -> None:
        if message.text.strip() == "❌ Отмена":
            await state.clear()
            await message.answer(MessageFormatter.operation_cancelled(), reply_markup=AdminKeyboard.main_menu())
            return
        query = message.text.strip()
        await state.clear()
        try:
            all_appts = await asyncio.to_thread(appt_service.get_appointments_filtered, "all")
            query_lower = query.lower()
            found = [
                a for a in all_appts
                if query_lower in (a.client_name or "").lower()
                or query in (a.phone or "")
            ]
            if not found:
                await message.answer(f"😔 История для «{query}» не найдена.")
                return
            text = MessageFormatter.admin_appointments_list(found[:20], filter_name=f"клиент {query}")
            await message.answer(text, parse_mode="HTML")
        except Exception as exc:
            logger.error("Ошибка истории клиента: %s", exc)
            await message.answer(MessageFormatter.error_general())

    # ════════════════════════════════════════════════════════════════════
    # РАЗДЕЛ 5: НАСТРОЙКИ
    # ════════════════════════════════════════════════════════════════════

    def _get_master_name() -> str:
        """FIXED HIGH-02: читает имя мастера из config.json вместо хардкода.
        
        Возвращает имя из config.json['master']['name'], иначе 'Мастер'.
        """
        try:
            from src.config.dependencies import _load_config_json
            config = _load_config_json()
            return config.get("master", {}).get("name", "Мастер")
        except Exception:
            return "Мастер"

    @router.message(F.text == "⚙️ Настройки")
    async def admin_settings(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        # FIXED HIGH-02: имя мастера из config.json, не хардкод
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
        # FIXED HIGH-02: имя мастера из config.json, не хардкод
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
    @router.callback_query(F.data == "admin_edit_welcome")
    async def admin_edit_welcome(callback: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        # Читаем текущий текст из config.json
        config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config.json")
        try:
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)
            current = config.get("bot", {}).get("welcome", "Текст не задан")
        except Exception:
            current = "Текст не задан"

        await state.set_state(AdminFSM.waiting_for_broadcast)  # Переиспользуем FSM
        await state.update_data(edit_mode="welcome")
        await callback.message.answer(
            f"Текущий текст приветствия:\n\n<i>{current[:200]}</i>\n\n"
            "Введите новый текст приветствия (поддерживается HTML):\n"
            "<i>Используйте {name} для вставки имени клиента</i>",
            reply_markup=AdminKeyboard.cancel(),
            parse_mode="HTML",
        )
        await callback.answer()

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

    # ── Обработчик текста при редактировании настроек ─────────────────────
    @router.message(AdminFSM.waiting_for_broadcast, F.text)
    async def admin_edit_setting_text(message: Message, state: FSMContext) -> None:
        if message.text.strip() == "❌ Отмена":
            await state.clear()
            await message.answer(MessageFormatter.operation_cancelled(), reply_markup=AdminKeyboard.main_menu())
            return

        data = await state.get_data()
        edit_mode = data.get("edit_mode")

        if edit_mode == "welcome":
            # FIXED HIGH-03: атомарная запись config.json:
            # 1. asyncio.Lock защищает от concurrent записей (race condition)
            # 2. Временный файл + os.replace() гарантирует атомарность (нет partial write)
            # 3. Инвалидация кэша _load_config_json — изменения видны сразу
            tmp_path = None
            async with _config_write_lock:
                config_path = os.path.normpath(
                    os.path.join(os.path.dirname(__file__), "..", "..", "config.json")
                )
                try:
                    # Читаем текущий конфиг
                    try:
                        with open(config_path, encoding="utf-8") as f:
                            config = json.load(f)
                    except FileNotFoundError:
                        config = {}

                    if "bot" not in config:
                        config["bot"] = {}
                    config["bot"]["welcome"] = message.text

                    # Атомарная запись: сначала во временный файл, потом os.replace()
                    import tempfile
                    config_dir = os.path.dirname(config_path)
                    with tempfile.NamedTemporaryFile(
                        mode="w",
                        encoding="utf-8",
                        dir=config_dir,
                        suffix=".tmp",
                        delete=False,
                    ) as tmp_f:
                        tmp_path = tmp_f.name
                        json.dump(config, tmp_f, ensure_ascii=False, indent=2)

                    os.replace(tmp_path, config_path)  # атомарная замена файла
                    tmp_path = None  # файл перемещён, удалять не нужно

                    # Инвалидируем кэш — изменения применяются без перезапуска
                    try:
                        from src.config.dependencies import _load_config_json
                        _load_config_json.cache_clear()
                    except Exception:
                        pass

                    await state.clear()
                    await message.answer(
                        "✅ Текст приветствия обновлён!\n\n"
                        "<i>Изменения применены немедленно</i>",
                        reply_markup=AdminKeyboard.main_menu(),
                        parse_mode="HTML",
                    )
                except Exception as exc:
                    logger.error("Ошибка обновления config.json: %s", exc)
                    # Удаляем временный файл если он остался
                    if tmp_path and os.path.exists(tmp_path):
                        try:
                            os.unlink(tmp_path)
                        except Exception:
                            pass
                    await message.answer(MessageFormatter.error_general())
            return

        # Обычная рассылка
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

    # ── Фото приветствия ──────────────────────────────────────────────────
    @router.callback_query(F.data == "admin_edit_photo")
    async def admin_edit_photo(callback: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminFSM.waiting_for_broadcast)
        await state.update_data(edit_mode="photo")
        await callback.message.answer(
            "📸 Отправьте URL фото для приветствия.\n\n"
            "<i>Фото должно быть доступно по прямой ссылке (https://...)</i>",
            reply_markup=AdminKeyboard.cancel(),
            parse_mode="HTML",
        )
        await callback.answer()

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
        except Exception:
            text = "🚫 <b>Чёрный список</b>\n\nОшибка получения списка."
        await message.answer(
            text,
            reply_markup=AdminKeyboard.blacklist_menu(),
            parse_mode="HTML",
        )

    @router.callback_query(F.data == "admin_show_blacklist")
    async def admin_show_blacklist(callback: CallbackQuery) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        try:
            blacklisted = await asyncio.to_thread(appt_service.get_blacklist)
            text = MessageFormatter.blacklist_info(blacklisted)
        except Exception:
            text = "🚫 <b>Чёрный список</b>\n\nСписок пуст или ошибка."
        await callback.message.edit_text(
            text,
            reply_markup=AdminKeyboard.blacklist_menu(),
            parse_mode="HTML",
        )
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

        # Если введён числовой ID
        if text.isdigit():
            user_id = int(text)
            try:
                if action == "block":
                    await asyncio.to_thread(appt_service.add_to_blacklist, user_id)
                    await message.answer(
                        MessageFormatter.blacklist_user_added(user_id),
                        reply_markup=AdminKeyboard.main_menu(),
                    )
                else:
                    await asyncio.to_thread(appt_service.remove_from_blacklist, user_id)
                    await message.answer(
                        MessageFormatter.blacklist_user_removed(user_id),
                        reply_markup=AdminKeyboard.main_menu(),
                    )
            except Exception as exc:
                logger.error("Ошибка изменения черного списка: %s", exc)
                await message.answer(f"❌ Ошибка: {exc}")
        else:
            # Поиск по имени
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

    @router.message(F.text == "📢 Рассылка")
    async def admin_broadcast_start(message: Message, state: FSMContext) -> None:
        if not _is_admin(message.from_user.id):
            return
        await state.set_state(AdminFSM.waiting_for_broadcast)
        await state.update_data(edit_mode="broadcast")
        await message.answer(
            "📢 Введите текст рассылки (поддерживается HTML):",
            reply_markup=AdminKeyboard.cancel(),
            parse_mode="HTML",
        )

    # FIXED CRIT-05: хранилище активных задач рассылки для предотвращения сборки GC
    _broadcast_tasks: set = set()

    @router.callback_query(F.data == "admin_broadcast_send")
    async def admin_broadcast_send(callback: CallbackQuery, state: FSMContext) -> None:
        """FIXED CRIT-05: рассылка запускается как фоновая задача (asyncio.create_task).
        
        Это предотвращает блокировку event loop на 50+ секунд при 1000+ пользователях.
        Задержка увеличена с 0.05с до 0.04с (соответствует лимиту Telegram ~25 msg/sec с запасом).
        Ссылка на задачу сохраняется в _broadcast_tasks для предотвращения преждевременной
        сборки мусора.
        """
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
            """Выполняет рассылку в фоне, не блокируя event loop."""
            try:
                all_user_ids: set[int] = set()
                try:
                    # FIXED HIGH-05: используем публичное .db свойство контейнера
                    db = getattr(container, "db", None) or getattr(container, "_db", None)
                    if db is not None:
                        def _get_all_users():
                            with db.read_connection() as conn:
                                rows = conn.execute("SELECT user_id FROM users").fetchall()
                                return {row[0] for row in rows}
                        all_user_ids = await asyncio.to_thread(_get_all_users)
                except Exception:
                    pass

                if not all_user_ids:
                    appts = await asyncio.to_thread(appt_service.get_all_active)
                    all_user_ids = {a.user_id for a in appts}

                sent = 0
                failed = 0
                for uid in all_user_ids:
                    try:
                        await callback.message.bot.send_message(uid, text, parse_mode="HTML")
                        sent += 1
                        # FIXED CRIT-05: задержка 0.04с ≈ 25 msg/sec (лимит Telegram 30/sec с запасом)
                        await asyncio.sleep(0.04)
                    except Exception:
                        failed += 1

                await callback.message.answer(
                    f"✅ Рассылка завершена: отправлено {sent}, ошибок {failed}.",
                    reply_markup=AdminKeyboard.main_menu(),
                )
            except Exception as exc:
                logger.error("Ошибка рассылки: %s", exc)
                try:
                    await callback.message.answer(MessageFormatter.error_general())
                except Exception:
                    pass

        # FIXED CRIT-05: запускаем как asyncio.create_task() — не блокируем event loop
        task = asyncio.create_task(_do_broadcast())
        # Сохраняем ссылку на задачу в _broadcast_tasks чтобы GC не удалил её раньше завершения
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
            import csv
            import io
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
            appointments = await asyncio.to_thread(appt_service.get_appointments_filtered, "all")
            day_appts = [a for a in appointments if a.date == date_str and not getattr(a, 'is_cancelled', False)]
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
            appointments = await asyncio.to_thread(appt_service.get_appointments_filtered, "all")
            day_appts = [a for a in appointments if a.date == date_str and not getattr(a, 'is_cancelled', False)]
            cancelled = 0
            for appt in day_appts:
                try:
                    await asyncio.to_thread(appt_service.admin_cancel_appointment, appt.id)
                    await notif_service.notify_client_cancellation_by_admin(appt.user_id, appt.date, appt.time)
                    cancelled += 1
                except Exception:
                    pass
            await callback.message.edit_text(
                f"✅ Отменено {cancelled} записей на {date_str}.",
                reply_markup=None,
            )
        except Exception as exc:
            logger.error("Ошибка массовой отмены: %s", exc)
            await callback.message.edit_text(MessageFormatter.error_general())
        await callback.answer()

    # NOTE: admin_monthly_stats handler removed from here — the more complete version
    # (with weekday breakdown and peak hours analysis) lives in extended_features_handler.py

    return router
