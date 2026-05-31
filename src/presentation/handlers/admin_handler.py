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
        import asyncio
        # Получаем статистику и количество свободных слотов
        stats = await asyncio.to_thread(appt_service.get_statistics)
        free_slots = 0
        try:
            if hasattr(sched_service, 'count_free_slots'):
                free_slots = await asyncio.to_thread(sched_service.count_free_slots)
        except Exception:
            free_slots = 0
        # FIXED: отправляем сводку дня в заголовке панели администратора
        text = MessageFormatter.admin_dashboard_summary(
            today=stats.get('today', 0),
            free_slots=free_slots,
            week=stats.get('week', 0),
            total=stats.get('total', 0),
            confirmed=stats.get('confirmed', 0),
        )
        await message.answer(
            text,
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
        import asyncio
        appointments = await asyncio.to_thread(appt_service.get_appointments_filtered, filter_key)
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

        import asyncio
        appt = await asyncio.to_thread(appt_service.get_appointment_by_id, appt_id)
        if not appt:
            await message.answer(MessageFormatter.appointment_not_found())
            try:
                await state.clear()
            except Exception:
                logger.exception("Failed to clear state in admin_cancel_by_id")
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
        import asyncio
        appt = await asyncio.to_thread(appt_service.get_appointment_by_id, appt_id)
        try:
            # FIXED: выполняем синхронную отмену в фоне
            await asyncio.to_thread(appt_service.admin_cancel_appointment, appt_id)
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
            try:
                await state.clear()
            except Exception:
                logger.exception("Failed to clear FSM state in admin_confirm_cancel")
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
                if is_opening:
                    sched_service.open_day(date_str)
                    await message.answer(MessageFormatter.admin_day_opened(date_str), reply_markup=AdminKeyboard.main_menu(), parse_mode="HTML")
                else:
                    sched_service.close_day(date_str)
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
            sched_service.ensure_working_day_exists(date_str)
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
            import asyncio
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

    # ── Админ: рассылка ───────────────────────────────────────────────────
    @router.message(F.text == "📢 Рассылка")
    async def admin_broadcast_start(message: Message, state: FSMContext) -> None:
        if not _is_admin(message.from_user.id):
            return
        await state.set_state(AdminFSM.waiting_for_broadcast)
        await message.answer("Отправьте текст рассылки (можно HTML):", reply_markup=AdminKeyboard.cancel(), parse_mode="HTML")

    @router.message(AdminFSM.waiting_for_broadcast, F.text)
    async def admin_broadcast_preview(message: Message, state: FSMContext) -> None:
        if message.text.strip() == "❌ Отмена":
            await state.clear()
            await message.answer(MessageFormatter.operation_cancelled(), reply_markup=AdminKeyboard.main_menu())
            return
        await state.update_data(broadcast_text=message.text)
        await message.answer("Предпросмотр рассылки:", parse_mode="HTML")
        await message.answer(message.text, parse_mode="HTML", reply_markup=AdminKeyboard.broadcast_confirm(message.text))

    @router.callback_query(F.data == "admin_broadcast_send")
    async def admin_broadcast_send(callback: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin(callback.from_user.id):
            await callback.answer()
            return
        data = await state.get_data()
        text = data.get("broadcast_text")
        if not text:
            await callback.answer("Нет текста для рассылки.")
            return
        await callback.answer("Рассылка запущена...")
        import asyncio
        try:
            appts = await asyncio.to_thread(appt_service.get_all)
            user_ids = {a.user_id for a in appts}
            sent = 0
            for uid in user_ids:
                try:
                    await callback.message.bot.send_message(uid, text, parse_mode="HTML")
                    sent += 1
                    await asyncio.sleep(0.05)
                except Exception:
                    logger.exception("Failed to send broadcast to %s", uid)
            await callback.message.edit_text(f"Рассылка завершена. Отправлено сообщений: {sent}")
        except Exception as exc:
            logger.exception("Broadcast failed: %s", exc)
            await callback.message.edit_text(MessageFormatter.error_general())
        finally:
            try:
                await state.clear()
            except Exception:
                pass

    @router.callback_query(F.data == "admin_broadcast_cancel")
    async def admin_broadcast_cancel(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await callback.message.edit_text(MessageFormatter.operation_cancelled())
        await callback.answer()

    # ── Админ: экспорт CSV ────────────────────────────────────────────────
    @router.message(F.text == "⬇️ Экспорт CSV")
    async def admin_export_csv_start(message: Message, state: FSMContext) -> None:
        if not _is_admin(message.from_user.id):
            return
        await state.set_state(AdminFSM.waiting_for_export_range)
        await message.answer("Введите диапазон дат для экспорта в формате YYYY-MM-DD:YYYY-MM-DD", reply_markup=AdminKeyboard.cancel())

    @router.message(AdminFSM.waiting_for_export_range, F.text)
    async def admin_export_csv_receive(message: Message, state: FSMContext) -> None:
        if message.text.strip() == "❌ Отмена":
            await state.clear()
            await message.answer(MessageFormatter.operation_cancelled(), reply_markup=AdminKeyboard.main_menu())
            return
        text = message.text.strip()
        import re, io, csv, asyncio
        m = re.match(r"^(\d{4}-\d{2}-\d{2}):(\d{4}-\d{2}-\d{2})$", text)
        if not m:
            await message.answer("Неверный формат. Пример: 2023-01-01:2023-01-31")
            return
        from_date, to_date = m.group(1), m.group(2)
        # Получим записи в фоне
        appts = await asyncio.to_thread(appt_service.get_by_date_range, from_date, to_date)
        if not appts:
            await message.answer("Записей за указанный период не найдено.")
            await state.clear()
            return
        # Генерируем CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "user_id", "username", "client_name", "phone", "date", "time", "service", "created_at", "is_cancelled"])
        for a in appts:
            writer.writerow([a.id, a.user_id, a.username, a.client_name, a.phone, a.date, a.time, a.service, a.created_at.strftime("%Y-%m-%d %H:%M:%S") if a.created_at else "", int(a.is_cancelled)])
        data = output.getvalue().encode("utf-8")
        import io as _io
        bio = _io.BytesIO(data)
        bio.name = f"appointments_{from_date}_to_{to_date}.csv"
        await message.answer_document(bio)
        await state.clear()

    # ── Админ: открыть неделю вперёд ─────────────────────────────────────
    @router.message(F.text == "📅 Открыть неделю")
    async def admin_open_week(message: Message) -> None:
        if not _is_admin(message.from_user.id):
            return
        # Создаём 7 дней вперёд с default slots, учитывая рабочие дни в настройках
        import asyncio
        from datetime import date as _date, timedelta
        today = _date.today()
        created = 0
        for i in range(7):
            d = today + timedelta(days=i)
            # Проверяем рабочие дни из настроек
            if d.isoweekday() not in settings.work_days:
                continue
            try:
                await asyncio.to_thread(sched_service.ensure_working_day_exists, d.isoformat())
                created += 1
            except Exception:
                logger.exception("Failed to create working day %s", d.isoformat())
        await message.answer(f"Открыто рабочих дней: {created}")

    # ── Админ: поиск клиента по имени/телефону ─────────────────────────────
    @router.message(F.text == "🔍 Найти клиента")
    async def admin_find_client_start(message: Message, state: FSMContext) -> None:
        if not _is_admin(message.from_user.id):
            return
        await state.set_state(AdminFSM.waiting_for_search_query)
        await message.answer("Введите имя или телефон клиента для поиска:", reply_markup=AdminKeyboard.cancel())

    @router.message(AdminFSM.waiting_for_search_query, F.text)
    async def admin_find_client_query(message: Message, state: FSMContext) -> None:
        if message.text.strip() == "❌ Отмена":
            await state.clear()
            await message.answer(MessageFormatter.operation_cancelled(), reply_markup=AdminKeyboard.main_menu())
            return
        q = message.text.strip()
        import asyncio
        results = await asyncio.to_thread(appt_service.search_appointments_by_client, q)
        if not results:
            await message.answer("Клиент не найден.")
            await state.clear()
            return
        await message.answer(MessageFormatter.admin_appointments_list(results, filter_name=f"по запросу {q}"), parse_mode="HTML")
        await state.clear()

    # ── Админ: черный список ─────────────────────────────────────────────
    @router.message(F.text == "🛑 Черный список")
    async def admin_blacklist_menu(message: Message, state: FSMContext) -> None:
        if not _is_admin(message.from_user.id):
            return
        await message.answer("Меню черного списка:", reply_markup=AdminKeyboard.blacklist_menu())

    @router.callback_query(F.data == "admin_block_user")
    async def admin_block_user_start(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(AdminFSM.waiting_for_blacklist_id)
        await callback.message.answer("Введите Telegram ID пользователя для блокировки:", reply_markup=AdminKeyboard.cancel())
        await callback.answer()

    @router.message(AdminFSM.waiting_for_blacklist_id, F.text)
    async def admin_block_user_receive(message: Message, state: FSMContext) -> None:
        if message.text.strip() == "❌ Отмена":
            await state.clear()
            await message.answer(MessageFormatter.operation_cancelled(), reply_markup=AdminKeyboard.main_menu())
            return
        try:
            user_id = int(message.text.strip())
        except ValueError:
            await message.answer("Неверный ID. Введите цифры.")
            return
        await state.update_data(block_user_id=user_id)
        await state.set_state(AdminFSM.waiting_for_block_reason)
        await message.answer("Введите причину блокировки (коротко):", reply_markup=AdminKeyboard.cancel())

    @router.message(AdminFSM.waiting_for_block_reason, F.text)
    async def admin_block_user_confirm(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        user_id = data.get("block_user_id")
        reason = message.text.strip()
        from datetime import datetime
        try:
            import asyncio
            # Вставляем запись в таблицу blacklist
            def _do_block():
                with appt_service._appointment_repo._db.transaction() as conn:
                    conn.execute("INSERT OR REPLACE INTO blacklist (user_id, reason, created_at) VALUES (?, ?, ?)", (user_id, reason, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            await asyncio.to_thread(_do_block)
            await message.answer(f"Пользователь {user_id} добавлен в черный список.")
        except Exception:
            logger.exception("Failed to block user %s", user_id)
            await message.answer(MessageFormatter.error_general())
        finally:
            await state.clear()

    @router.callback_query(F.data == "admin_unblock_user")
    async def admin_unblock_user(callback: CallbackQuery) -> None:
        await callback.answer()
        await callback.message.answer("Введите Telegram ID для разблокировки:")

    # ── Админ: отмена всех записей на день (экстренная) ──────────────────
    @router.message(F.text == "🚫 Отменить все записи на дату")
    async def admin_cancel_all_start(message: Message, state: FSMContext) -> None:
        if not _is_admin(message.from_user.id):
            return
        await state.set_state(AdminFSM.confirming_cancel_all)
        await message.answer("Введите дату YYYY-MM-DD для массовой отмены:", reply_markup=AdminKeyboard.cancel())

    @router.message(AdminFSM.confirming_cancel_all, F.text)
    async def admin_cancel_all_execute(message: Message, state: FSMContext) -> None:
        if message.text.strip() == "❌ Отмена":
            await state.clear()
            await message.answer(MessageFormatter.operation_cancelled(), reply_markup=AdminKeyboard.main_menu())
            return
        date_str = message.text.strip()
        import asyncio
        try:
            # Отменяем все записи на дату и уведомляем клиентов
            appts = await asyncio.to_thread(appt_service.get_by_date, date_str)
            count = 0
            for a in appts:
                try:
                    await asyncio.to_thread(appt_service.admin_cancel_appointment, a.id)
                    await notif_service.notify_client_cancellation_by_admin(a.user_id, a.date, a.time)
                    count += 1
                except Exception:
                    logger.exception("Failed to cancel appointment %s", a.id)
            await message.answer(f"Отменено записей: {count}")
        except Exception:
            logger.exception("Failed to cancel all appointments on %s", date_str)
            await message.answer(MessageFormatter.error_general())
        finally:
            await state.clear()

    # ── Навигация назад ───────────────────────────────────────────────────
    @router.callback_query(F.data == "admin_back_main")
    async def admin_back_main(callback: CallbackQuery) -> None:
        await callback.message.edit_text(
            MessageFormatter.admin_welcome(),
            reply_markup=None,
            parse_mode="HTML",
        )
        await callback.answer()

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
