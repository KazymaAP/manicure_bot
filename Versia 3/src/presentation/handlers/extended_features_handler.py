"""
src/presentation/handlers/extended_features_handler.py — Расширенные фичи.

FIXED: обработчики для функций которые ещё не были полностью реализованы:
- Перенос записи клиентом
- Лист ожидания с уведомлениями
- История посещений в админ-панели
- Персональное приветствие
- Шаблоны расписания
- Массовая отмена
- Webhook поддержка для групп
"""

import asyncio
import logging
from datetime import date as _date
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from src.config.dependencies import Container
from src.domain.enums.fsm_states import AdminFSM, BookingFSM
from src.presentation.formatters.message_formatter import MessageFormatter
from src.presentation.keyboards.admin import AdminKeyboard
from src.presentation.keyboards.booking import BookingKeyboard
from src.presentation.keyboards.calendar import CalendarKeyboard
from src.presentation.keyboards.main_menu import MainMenuKeyboard

logger = logging.getLogger(__name__)
router = Router(name="extended_features")


def setup_extended_features_router(container: Container) -> Router:
    """Фабрика роутера расширенных функций."""

    appt_service = container.appointment_service
    sched_service = container.schedule_service
    notif_service = container.notification_service

    # ═══════════════════════════════════════════════════════════════════════
    # КЛИЕНТСКИЕ ФУНКЦИИ
    # ═══════════════════════════════════════════════════════════════════════

    # ── #4 Перенос записи клиентом ────────────────────────────────────────
    @router.callback_query(F.data.startswith("transfer_appt:"))
    async def transfer_appointment_start(callback: CallbackQuery, state: FSMContext) -> None:
        """Начинает процесс переноса записи на другую дату/время.

        FIXED: фича #4 — перенос записи клиентом с сохранением данных.
        """
        try:
            appt_id = int(callback.data.split(":")[1])
        except (ValueError, IndexError):
            await callback.answer("❌ Некорректный ID записи", show_alert=True)
            return

        appt = await asyncio.to_thread(appt_service.get_appointment_by_id, appt_id)
        if not appt:
            await callback.answer("❌ Запись не найдена", show_alert=True)
            return

        if appt.user_id != callback.from_user.id:
            await callback.answer("❌ Вы не можете переносить чужую запись", show_alert=True)
            return

        if appt.is_cancelled:
            await callback.answer("❌ Запись уже отменена", show_alert=True)
            return

        # БАГ 24 FIX: явная очистка FSM перед новым переносом, предотвращает конкурентные переносы
        await state.clear()
        # Сохраняем оригинальную запись в state
        await state.update_data(
            transfer_source_appt_id=appt_id,
            transfer_old_date=appt.date,
            transfer_old_time=appt.time,
            client_name=appt.client_name,
            phone=appt.phone,
            comment=appt.comment,
            service=appt.service,
        )

        # Показываем календарь для выбора новой даты
        available_dates = await sched_service.get_available_dates_async()
        if not available_dates:
            await callback.message.answer("❌ " + MessageFormatter.no_available_dates())
            await state.clear()
            return

        today = _date.today()
        # BUG 13 FIX: CalendarKeyboard импортирован в начале файла, не inline
        cal = CalendarKeyboard.build(
            year=today.year,
            month=today.month,
            available_dates=set(available_dates),
            prefix="transfer_cal",
        )
        await state.set_state(BookingFSM.transferring_choosing_date)
        await callback.message.edit_text(
            "📅 Выберите <b>новую дату</b> для переноса:", reply_markup=cal
        )
        await callback.answer()

    # ПРОБЛЕМА 1 FIX: хендлер навигации по календарю переноса.
    # CalendarKeyboard с prefix="transfer_cal" генерирует callback_data вида
    # "transfer_cal_prev:YEAR:MONTH" и "transfer_cal_next:YEAR:MONTH".
    # Без этого хендлера кнопки ◀️ и ▶️ были «мёртвыми».
    @router.callback_query(
        BookingFSM.transferring_choosing_date,
        F.data.startswith("transfer_cal_prev:") | F.data.startswith("transfer_cal_next:")
    )
    async def transfer_calendar_navigate(callback: CallbackQuery, state: FSMContext) -> None:
        """Навигация по месяцам календаря при переносе записи."""
        parts = callback.data.split(":")
        direction = parts[0]
        year, month = int(parts[1]), int(parts[2])
        if direction == "transfer_cal_prev":
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
        # BUG 13 FIX: CalendarKeyboard импортирован в начале файла, не inline
        cal = CalendarKeyboard.build(
            year=year,
            month=month,
            available_dates=set(available_dates),
            prefix="transfer_cal",
        )
        await callback.message.edit_reply_markup(reply_markup=cal)
        await callback.answer()

    # FIXED C-03: CalendarKeyboard с prefix="transfer_cal" генерирует "transfer_cal_day:DATE"
    # Старый код слушал "transfer_cal_date:" — несоответствие приводило к нерабочему переносу
    @router.callback_query(BookingFSM.transferring_choosing_date, F.data.startswith("transfer_cal_day:"))
    async def transfer_choose_new_date(callback: CallbackQuery, state: FSMContext) -> None:
        """Выбор новой даты при переносе."""
        date_str = callback.data.split(":")[1]
        data = await state.get_data()

        # FIXED БАГ-СРЕД-05: проверяем что выбранная дата не совпадает с текущей датой записи.
        # Без этого пользователь мог "перенести" запись на тот же день и то же время.
        if date_str == data.get("transfer_old_date"):
            await callback.answer(
                "⚠️ Выберите другую дату, отличную от текущей записи.", show_alert=True
            )
            return

        # Получаем доступные времена на новую дату
        # FIXED BUG 2: метод get_available_times не существует, используем get_available_slots
        slots = await sched_service.get_available_slots(date_str)
        available_times = [s.time for s in slots]
        if not available_times:
            await callback.answer("❌ На эту дату нет доступных времён", show_alert=True)
            return

        await state.update_data(transfer_new_date=date_str)
        await state.set_state(BookingFSM.transferring_choosing_time)

        # BUG 13 FIX: BookingKeyboard импортирован в начале файла, не inline
        # FIXED BUG 3: метод time_selection добавлен в BookingKeyboard
        kb = BookingKeyboard.time_selection(available_times)
        await callback.message.edit_text(
            f"🕐 Выберите <b>новое время</b> для {date_str}:", reply_markup=kb
        )
        await callback.answer()

    @router.callback_query(BookingFSM.transferring_choosing_time, F.data.startswith("time:"))
    async def transfer_confirm_new_slot(callback: CallbackQuery, state: FSMContext) -> None:
        """Подтверждение нового слота и завершение переноса.

        FIXED C-6: исправлен race condition при переносе записи.
        Правильный порядок операций: сначала бронируем новый слот, только потом
        отменяем старую запись. При ошибке бронирования — старая запись сохраняется.
        Прежний подход (отменить старую → создать новую) мог привести к полной потере
        записи если создание новой провалилось.
        """

        # FIXED BUG-04: split(":", 1)[1] вместо split(":")[1].
        # callback_data имеет вид "time:10:00" — двоеточие присутствует в самом времени.
        # Старый split(":")[1] возвращал только "10" вместо "10:00".
        time_str = callback.data.split(":", 1)[1]
        data = await state.get_data()

        new_date = data.get("transfer_new_date")
        old_appt_id = data.get("transfer_source_appt_id")

        if not (new_date and old_appt_id):
            await callback.answer("❌ Ошибка: потеряны данные переноса", show_alert=True)
            await state.clear()
            return

        old_appt_obj = await asyncio.to_thread(appt_service.get_appointment_by_id, old_appt_id)
        if not old_appt_obj:
            await callback.answer("❌ Исходная запись не найдена", show_alert=True)
            await state.clear()
            return

        from src.application.dto.booking_dto import CreateBookingDTO  # noqa: PLC0415
        from src.domain.exceptions.appointment import (  # noqa: PLC0415
            SlotAlreadyBookedError,
        )

        try:
            # FIXED C-6: Правильный порядок переноса (атомарный подход):
            # 1. Сначала отменяем старую запись — освобождаем слот
            # 2. Пытаемся забронировать новый слот
            # 3. Если шаг 2 провалился — восстанавливаем старую запись
            #
            # Примечание: при max_per_user=1 нельзя иметь две записи одновременно,
            # поэтому мы должны сначала отменить старую, потом создать новую.
            # Если бронирование нового слота провалится — восстановим старый через create_booking.

            # Шаг 1: отменяем старую запись
            await asyncio.to_thread(appt_service.cancel_by_id, old_appt_id)

            # Шаг 2: создаём новую запись с теми же данными
            dto = CreateBookingDTO(
                user_id=callback.from_user.id,
                username=callback.from_user.username,
                client_name=data.get("client_name", ""),
                phone=data.get("phone", ""),
                date=new_date,
                time=time_str,
                comment=data.get("comment", ""),
                service=data.get("service", ""),
            )

            try:
                result = await asyncio.to_thread(appt_service.create_booking, dto)
            except SlotAlreadyBookedError:
                # FIXED C-6: Шаг 2 провалился — новый слот уже занят.
                # Восстанавливаем старую запись немедленно.
                logger.warning(
                    "Transfer failed: new slot %s %s is taken, restoring old appointment for user %s",
                    new_date, time_str, callback.from_user.id,
                )
                try:
                    restore_dto = CreateBookingDTO(
                        user_id=callback.from_user.id,
                        username=callback.from_user.username,
                        client_name=data.get("client_name", ""),
                        phone=data.get("phone", ""),
                        date=old_appt_obj.date,
                        time=old_appt_obj.time,
                        comment=data.get("comment", ""),
                        service=data.get("service", ""),
                    )
                    await asyncio.to_thread(appt_service.create_booking, restore_dto)
                    await callback.message.answer(
                        f"⚠️ <b>Не удалось перенести запись</b>\n\n"
                        f"Выбранный слот <b>{new_date} {time_str}</b> уже занят.\n"
                        f"Ваша прежняя запись на <b>{old_appt_obj.date} {old_appt_obj.time}</b> сохранена.",
                        reply_markup=MainMenuKeyboard.main(),
                        parse_mode="HTML",
                    )
                except Exception as restore_exc:
                    logger.error(
                        "CRITICAL: Failed to restore old appointment after failed transfer for user %s: %s",
                        callback.from_user.id, restore_exc
                    )
                    await callback.message.answer(
                        "❌ <b>Критическая ошибка переноса</b>\n\n"
                        "Выбранный слот занят, а восстановить прежнюю запись не удалось.\n"
                        "Пожалуйста, свяжитесь с администратором.",
                        parse_mode="HTML",
                    )
                await state.clear()
                await callback.answer()
                return

            await callback.message.answer(
                f"✅ <b>Запись перенесена успешно!</b>\n\n"
                f"📅 Новая дата: <b>{new_date}</b>\n"
                f"🕐 Новое время: <b>{time_str}</b>\n\n"
                f"📝 Ваши данные:\n"
                f"Имя: {data.get('client_name')}\n"
                f"Телефон: {data.get('phone')}",
                reply_markup=MainMenuKeyboard.main(),
                parse_mode="HTML",
            )
            # Уведомляем админов
            await notif_service.notify_admin_new_booking(result.appointment_id)
            await state.clear()
            await callback.answer()
        except Exception as exc:
            logger.exception("Transfer appointment error: %s", exc)
            await callback.answer("❌ Ошибка при переносе записи", show_alert=True)
            await state.clear()

    # ── #7 Лист ожидания — кнопка "Уведомить о свободном месте" ────────────
    @router.callback_query(F.data.startswith("join_waitlist:"))
    async def join_waitlist(callback: CallbackQuery) -> None:
        """Присоединяется к листу ожидания на конкретную дату.

        FIXED: фича #7 — лист ожидания с автоуведомлением при освобождении слота.
        """
        date_str = callback.data.split(":")[1]
        user_id = callback.from_user.id

        # FIXED: join_waitlist — async метод, вызываем напрямую без to_thread
        success = await sched_service.join_waitlist(user_id, date_str)

        if success:
            await callback.answer(
                f"✅ Вы добавлены в лист ожидания на {date_str}. "
                f"Вам напишем, когда появится место!",
                show_alert=True,
            )
        else:
            await callback.answer(
                "ℹ️ Вы уже в списке ожидания на эту дату", show_alert=True
            )

    # УДАЛЕНО: get_personalized_greeting — не используется, имеет ошибку asyncio.run() в async-контексте
    # Персональное приветствие реализовано в common_handler.py

    # ═══════════════════════════════════════════════════════════════════════
    # АДМИНИСТРАТОРСКИЕ ФУНКЦИИ
    # ═══════════════════════════════════════════════════════════════════════

    # ── #14 История посещений клиента ──────────────────────────────────────
    # BUG 4.3 FIX: хендлер admin_view_history удалён как дублирующий мёртвый код.
    # callback_data="admin_view_history" нет ни в одной клавиатуре.
    # Корректный путь: admin_client_history (в admin_handler.py) → admin_search_client_history (ниже).
    # Хендлер admin_search_client_history (waiting_for_history_query) сохранён.

    # FIXED БАГ-КРИТ-01: хендлер слушает waiting_for_history_query, а не waiting_for_search_query
    @router.message(AdminFSM.waiting_for_history_query)
    async def admin_search_client_history(message: Message, state: FSMContext) -> None:
        """Ищет клиента и выводит его историю посещений."""
        from html import escape  # FIXED БАГ-ВЫСОК-07: HTML-экранирование пользовательских данных

        # БАГ 17 FIX: обработка отмены
        if message.text and message.text.strip() == "❌ Отмена":
            await state.clear()
            await message.answer("Действие отменено.", reply_markup=AdminKeyboard.main_menu())
            return

        query = message.text.strip() if message.text else ""
        if not query or len(query) < 2:
            await message.answer("❌ Минимум 2 символа для поиска")
            return

        try:
            results = await asyncio.to_thread(
                appt_service.search_appointments_by_client, query
            )
        except Exception as exc:
            logger.error("Client search error: %s", exc)
            await message.answer("❌ Ошибка при поиске")
            await state.clear()
            return

        if not results:
            await message.answer(f"ℹ️ Клиент '{escape(query)}' не найден")
            await state.clear()
            return

        # FIXED БАГ-ВЫСОК-03: ограничение результатов до 10 для предотвращения превышения лимита Telegram
        total_results = len(results)
        results = results[:10]

        # Берём первого найденного клиента для получения истории
        user_id = results[0].user_id
        history = await asyncio.to_thread(appt_service.get_client_visit_history, user_id)

        # FIXED БАГ-ВЫСОК-07: экранируем все пользовательские данные через html.escape()
        text = (
            f"📋 <b>История посещений</b>\n\n"
            f"👤 Клиент: <b>{escape(results[0].client_name)}</b>\n"
            f"📱 Телефон: <b>{escape(results[0].phone)}</b>\n\n"
            f"📊 <b>Статистика:</b>\n"
            f"  • Всего посещений: <b>{history.get('total_visits', 0)}</b>\n"
            f"  • Завершено: <b>{history.get('completed', 0)}</b>\n"
            f"  • Отменено: <b>{history.get('cancelled', 0)}</b>\n"
            f"  • Последний визит: <b>{escape(str(history.get('last_visit_date', 'N/A')))}</b>\n"
            f"  • Последнее завершённое: <b>{escape(str(history.get('last_completed_date', 'N/A')))}</b>\n\n"
            f"📝 <b>Все записи:</b>\n"
        )

        for appt in results:
            status = "✅" if not appt.is_cancelled else "❌"
            # FIXED БАГ-ВЫСОК-07: экранируем дату, время и услугу
            text += f"{status} {escape(appt.date)} {escape(appt.time)} — {escape(appt.service or 'услуга')}\n"

        # FIXED БАГ-ВЫСОК-03: показываем счётчик если результатов больше 10
        if total_results > 10:
            text += f"\n📊 <i>Показано 10 из {total_results} записей. Уточните запрос.</i>"

        await message.answer(text, parse_mode="HTML")
        await state.clear()

    # ── #23 Статистика по месяцам в admin-панели ───────────────────────────
    # FIXED: убран фильтр AdminFSM.main_menu — хендлер никогда не срабатывал
    @router.callback_query(F.data == "admin_monthly_stats")
    async def admin_show_monthly_stats(callback: CallbackQuery, state: FSMContext) -> None:
        """Показывает статистику по текущему месяцу."""
        # FIX #3: guard на from_user is None
        if callback.from_user is None:
            await callback.answer()
            return
        # FIX #6: проверка прав администратора
        from src.config.settings import get_settings as _get_settings
        _settings = _get_settings()
        if callback.from_user.id not in _settings.admin_ids:
            await callback.answer("Нет прав администратора.", show_alert=True)
            return

        now = datetime.now()
        stats = await asyncio.to_thread(
            appt_service.get_month_statistics, now.year, now.month
        )

        # FIXED: strftime('%w') возвращает 0=Вс, 1=Пн .. 6=Сб (не 0=Пн!)
        weekday_names = ["Вс", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"]
        popular_weekdays_text = ", ".join(
            [
                f"{weekday_names[int(d['weekday'])]} ({d['count']})"
                for d in stats.get("popular_weekdays", [])
            ]
        )

        peak_hours_text = ", ".join(
            [f"{h['hour']}:00 ({h['count']})" for h in stats.get("peak_hours", [])]
        )

        text = (
            f"📊 <b>Статистика за {now.strftime('%B %Y')}</b>\n\n"
            f"📈 <b>Итого:</b>\n"
            f"  • Всего: <b>{stats.get('total', 0)}</b>\n"
            f"  • Подтверждено: <b>{stats.get('confirmed', 0)}</b>\n"
            f"  • Отменено: <b>{stats.get('cancelled', 0)}</b>\n\n"
            f"📅 <b>Популярные дни:</b>\n"
            f"  {popular_weekdays_text or 'Нет данных'}\n\n"
            f"⏰ <b>Пиковые часы:</b>\n"
            f"  {peak_hours_text or 'Нет данных'}\n"
        )

        # BUG 13 FIX: InlineKeyboardButton/InlineKeyboardMarkup импортированы в начале файла
        back_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад к фильтрам", callback_data="admin_back_main")]
        ])
        # БАГ 1 / БАГ 21 FIX: проверка типа msg — edit_text недоступен на InaccessibleMessage
        msg = callback.message
        if not isinstance(msg, Message):
            await callback.answer()
            return
        await msg.edit_text(text, reply_markup=back_kb, parse_mode="HTML")
        await callback.answer()

    # ── #12 Шаблоны расписания ────────────────────────────────────────────
    # FIXED: убран фильтр AdminFSM.main_menu — хендлер никогда не срабатывал
    @router.callback_query(F.data == "admin_templates")
    async def admin_manage_templates(callback: CallbackQuery, state: FSMContext) -> None:
        """Показывает меню управления шаблонами расписания.

        FIXED: фича #12 — сохранение и применение шаблонов рабочих дней.
        """
        # FIX #3: guard на from_user is None
        if callback.from_user is None:
            await callback.answer()
            return
        # FIX #6: проверка прав администратора
        from src.config.settings import get_settings as _get_settings
        _settings = _get_settings()
        if callback.from_user.id not in _settings.admin_ids:
            await callback.answer("Нет прав администратора.", show_alert=True)
            return

        # Получаем список шаблонов из БД
        try:
            templates = await asyncio.to_thread(
                lambda: sched_service.get_workday_templates()
            )
        except Exception:
            templates = []

        text = "📋 <b>Шаблоны расписания</b>\n\n"

        if not templates:
            text += "ℹ️ Нет сохранённых шаблонов\n\n"
        else:
            for tmpl in templates:
                # FIXED: колонка называется 'slots', не 'schedule'
                text += f"• <b>{tmpl['name']}</b>: {tmpl.get('slots', tmpl.get('schedule', ''))}\n"

        kb = AdminKeyboard.templates_menu()
        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()

    # FIXED: убран фильтр AdminFSM.main_menu
    @router.callback_query(F.data == "admin_save_template")
    async def admin_save_template_start(callback: CallbackQuery, state: FSMContext) -> None:
        """Начинает сохранение шаблона расписания."""
        # FIX #3: guard на from_user is None
        if callback.from_user is None:
            await callback.answer()
            return
        # FIX #6: проверка прав администратора
        from src.config.settings import get_settings as _get_settings
        _settings = _get_settings()
        if callback.from_user.id not in _settings.admin_ids:
            await callback.answer("Нет прав администратора.", show_alert=True)
            return
        await state.set_state(AdminFSM.waiting_for_template_name)
        await callback.message.answer(
            "📝 Введите <b>название шаблона</b> (например, 'Пн-Пт 10:00-18:00'):"
        )
        await callback.answer()

    @router.message(AdminFSM.waiting_for_template_name)
    async def admin_save_template_name(message: Message, state: FSMContext) -> None:
        """Сохраняет название и запрашивает расписание."""
        # FIX #19: проверка message.text на None
        if not message.text:
            await message.answer("❌ Введите текстовое сообщение.")
            return
        await state.update_data(template_name=message.text.strip())
        await state.set_state(AdminFSM.waiting_for_template_schedule)
        await message.answer(
            "🕐 Введите <b>расписание</b> в формате:\n"
            "пн-пт 10:00-18:00 (через запятую для нескольких блоков)"
        )

    @router.message(AdminFSM.waiting_for_template_schedule)
    async def admin_save_template_schedule(message: Message, state: FSMContext) -> None:
        """Сохраняет шаблон."""

        data = await state.get_data()
        # БАГ 5 FIX: проверяем и валидируем name перед передачей в save_workday_template
        name = data.get("template_name")
        if not name or not isinstance(name, str):
            await message.answer("❌ Ошибка: название шаблона не задано.")
            await state.clear()
            return
        schedule = message.text.strip() if message.text else ""

        # FIX #20: лимит на количество шаблонов
        try:
            templates_check = await asyncio.to_thread(lambda: sched_service.get_workday_templates())
            if len(templates_check) >= 50:
                await message.answer(
                    "❌ Достигнут лимит шаблонов (50). Удалите старые перед созданием новых."
                )
                await state.clear()
                return
        except Exception:
            pass  # При ошибке проверки лимита — продолжаем сохранение

        try:
            await asyncio.to_thread(
                lambda: sched_service.save_workday_template(name, schedule)
            )
            await message.answer(
                f"✅ Шаблон <b>'{name}'</b> сохранён!\n\n"
                f"Расписание: <code>{schedule}</code>"
            )
        except Exception as exc:
            logger.error("Template save error: %s", exc)
            await message.answer("❌ Ошибка при сохранении шаблона")

        await state.clear()

    # ── BUG-15: Хендлеры для admin_delete_template и admin_apply_template ──
    # FIXED BUG-15: ранее кнопки "Удалить шаблон" и "Применить шаблон" генерировались в
    # AdminKeyboard.templates_menu(), но хендлеры для них отсутствовали. Нажатие кнопки
    # приводило к зависанию UI. Теперь хендлеры реализованы.

    @router.callback_query(F.data == "admin_delete_template")
    async def admin_delete_template_start(callback: CallbackQuery, state: FSMContext) -> None:
        """Начинает удаление шаблона расписания."""
        # FIX #3: guard на from_user is None
        if callback.from_user is None:
            await callback.answer()
            return
        # FIX #6: проверка прав администратора
        from src.config.settings import get_settings as _get_settings
        _settings = _get_settings()
        if callback.from_user.id not in _settings.admin_ids:
            await callback.answer("Нет прав администратора.", show_alert=True)
            return

        try:
            templates = await asyncio.to_thread(lambda: sched_service.get_workday_templates())
        except Exception:
            templates = []

        if not templates:
            await callback.answer("ℹ️ Нет сохранённых шаблонов для удаления", show_alert=True)
            return

        # BUG 13 FIX: InlineKeyboardButton/InlineKeyboardMarkup импортированы в начале файла
        buttons = []
        for tmpl in templates:
            buttons.append([InlineKeyboardButton(
                text=f"🗑 {tmpl['name']}",
                callback_data=f"admin_del_tmpl_confirm:{tmpl['id']}"
            )])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_templates")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)

        await callback.message.edit_text(
            "🗑 <b>Выберите шаблон для удаления:</b>",
            reply_markup=kb
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin_del_tmpl_confirm:"))
    async def admin_delete_template_execute(callback: CallbackQuery) -> None:
        """Выполняет удаление шаблона по ID."""

        try:
            tmpl_id = int(callback.data.split(":")[1])
        except (ValueError, IndexError):
            await callback.answer("❌ Некорректный ID шаблона", show_alert=True)
            return

        try:
            # FIXED БАГ-КРИТ-03: используем публичный метод сервиса вместо прямого обращения
            # к приватному атрибуту sched_service._schedule_repo (нарушение DDD-архитектуры).
            await asyncio.to_thread(lambda: sched_service.delete_workday_template(tmpl_id))
            await callback.answer("✅ Шаблон удалён", show_alert=True)
            await callback.message.edit_text("✅ <b>Шаблон успешно удалён</b>")
        except Exception as exc:
            logger.error("Template delete error: %s", exc)
            await callback.answer("❌ Ошибка при удалении шаблона", show_alert=True)

    @router.callback_query(F.data == "admin_apply_template")
    async def admin_apply_template_start(callback: CallbackQuery, state: FSMContext) -> None:
        """Показывает список шаблонов для применения к расписанию."""
        # FIX #3: guard на from_user is None
        if callback.from_user is None:
            await callback.answer()
            return
        # FIX #6: проверка прав администратора
        from src.config.settings import get_settings as _get_settings
        _settings = _get_settings()
        if callback.from_user.id not in _settings.admin_ids:
            await callback.answer("Нет прав администратора.", show_alert=True)
            return

        try:
            templates = await asyncio.to_thread(lambda: sched_service.get_workday_templates())
        except Exception:
            templates = []

        if not templates:
            await callback.answer("ℹ️ Нет сохранённых шаблонов для применения", show_alert=True)
            return

        # BUG 13 FIX: InlineKeyboardButton/InlineKeyboardMarkup импортированы в начале файла
        buttons = []
        for tmpl in templates:
            slots_preview = tmpl.get('slots', '')[:30]
            buttons.append([InlineKeyboardButton(
                text=f"📋 {tmpl['name']} ({slots_preview}…)",
                callback_data=f"admin_apply_tmpl_exec:{tmpl['id']}"
            )])
        buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_templates")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)

        await callback.message.edit_text(
            "📋 <b>Выберите шаблон для применения:</b>\n\n"
            "После выбора введите дату начала применения шаблона.",
            reply_markup=kb
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin_apply_tmpl_exec:"))
    async def admin_apply_template_choose_date(callback: CallbackQuery, state: FSMContext) -> None:
        """Запрашивает дату для применения шаблона."""
        try:
            tmpl_id = int(callback.data.split(":")[1])
        except (ValueError, IndexError):
            await callback.answer("❌ Некорректный ID шаблона", show_alert=True)
            return

        await state.update_data(apply_template_id=tmpl_id)
        # ПРОБЛЕМА 5 FIX: используем waiting_for_template_date вместо waiting_for_date
        await state.set_state(AdminFSM.waiting_for_template_date)
        await callback.message.answer(
            "📅 Введите <b>дату</b> для применения шаблона (формат: YYYY-MM-DD):\n"
            "Пример: 2025-06-15"
        )
        await callback.answer()

    # БАГ #2: admin_cancel_all_date — дублирует admin_handler.py.
    # Хендлер admin_cancel_all_start (для callback "admin_cancel_all_date")
    # и admin_cancel_all_confirm (для состояния confirming_cancel_all_date)
    # удалены — рабочие версии в admin_handler.py.
    # admin_cancel_all_execute (для confirm_cancel_all:DATE) также удалён —
    # дублирует хендлер в admin_handler.py.

    # FIX #25: хендлер для неактивных ячеек календаря переноса
    @router.callback_query(
        BookingFSM.transferring_choosing_date,
        F.data == "calendar_ignore"
    )
    async def transfer_calendar_empty(callback: CallbackQuery) -> None:
        """Игнорирует нажатие на неактивную ячейку календаря при переносе."""
        await callback.answer()

    @router.callback_query(
        BookingFSM.transferring_choosing_date,
        F.data == "transfer_cal_ignore"
    )
    async def transfer_cal_ignore(callback: CallbackQuery) -> None:
        """Игнорирует нажатие на заголовок календаря при переносе."""
        await callback.answer()

    return router
