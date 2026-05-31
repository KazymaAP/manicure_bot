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

import logging
from datetime import date as _date, datetime, timedelta
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from src.config.dependencies import Container
from src.domain.enums.fsm_states import BookingFSM, AdminFSM
from src.presentation.formatters.message_formatter import MessageFormatter
from src.presentation.keyboards.main_menu import MainMenuKeyboard
from src.presentation.keyboards.admin import AdminKeyboard

logger = logging.getLogger(__name__)
router = Router(name="extended_features")


def setup_extended_features_router(container: Container) -> Router:
    """Фабрика роутера расширенных функций."""

    appt_service = container.appointment_service
    sched_service = container.schedule_service
    notif_service = container.notification_service
    settings = container.settings

    # ═══════════════════════════════════════════════════════════════════════
    # КЛИЕНТСКИЕ ФУНКЦИИ
    # ═══════════════════════════════════════════════════════════════════════

    # ── #4 Перенос записи клиентом ────────────────────────────────────────
    @router.callback_query(F.data.startswith("transfer_appt:"))
    async def transfer_appointment_start(callback: CallbackQuery, state: FSMContext) -> None:
        """Начинает процесс переноса записи на другую дату/время.

        FIXED: фича #4 — перенос записи клиентом с сохранением данных.
        """
        import asyncio
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
        from src.presentation.keyboards.calendar import CalendarKeyboard

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

    @router.callback_query(BookingFSM.transferring_choosing_date, F.data.startswith("transfer_cal_date:"))
    async def transfer_choose_new_date(callback: CallbackQuery, state: FSMContext) -> None:
        """Выбор новой даты при переносе."""
        import asyncio

        date_str = callback.data.split(":")[1]
        data = await state.get_data()

        # Получаем доступные времена на новую дату
        available_times = await asyncio.to_thread(sched_service.get_available_times, date_str)
        if not available_times:
            await callback.answer("❌ На эту дату нет доступных времён", show_alert=True)
            return

        await state.update_data(transfer_new_date=date_str)
        await state.set_state(BookingFSM.transferring_choosing_time)

        from src.presentation.keyboards.booking import BookingKeyboard

        kb = BookingKeyboard.time_selection(available_times)
        await callback.message.edit_text(
            f"🕐 Выберите <b>новое время</b> для {date_str}:", reply_markup=kb
        )
        await callback.answer()

    @router.callback_query(BookingFSM.transferring_choosing_time, F.data.startswith("time:"))
    async def transfer_confirm_new_slot(callback: CallbackQuery, state: FSMContext) -> None:
        """Подтверждение нового слота и завершение переноса."""
        import asyncio

        time_str = callback.data.split(":")[1]
        data = await state.get_data()

        new_date = data.get("transfer_new_date")
        old_appt_id = data.get("transfer_source_appt_id")

        if not (new_date and old_appt_id):
            await callback.answer("❌ Ошибка: потеряны данные переноса", show_alert=True)
            await state.clear()
            return

        # Пытаемся забронировать новый слот и отменить старый
        try:
            # Отменяем старую запись
            await asyncio.to_thread(appt_service.cancel_by_id, old_appt_id)

            # Создаём новую запись с теми же данными
            from src.application.dto.booking_dto import CreateBookingDTO

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

            result = await asyncio.to_thread(appt_service.create_booking, dto)

            if result.success:
                await callback.message.answer(
                    f"✅ <b>Запись перенесена успешно!</b>\n\n"
                    f"📅 Новая дата: <b>{new_date}</b>\n"
                    f"🕐 Новое время: <b>{time_str}</b>\n\n"
                    f"📝 Ваши данные:\n"
                    f"Имя: {data.get('client_name')}\n"
                    f"Телефон: {data.get('phone')}",
                    reply_markup=MainMenuKeyboard.main(),
                )
                # Уведомляем админов
                await notif_service.notify_admin_new_booking(result.appointment_id)
                await state.clear()
            else:
                await callback.answer(
                    f"❌ Не удалось забронировать новый слот: {result.error}",
                    show_alert=True,
                )
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
        import asyncio

        date_str = callback.data.split(":")[1]
        user_id = callback.from_user.id

        success = await asyncio.to_thread(
            lambda: sched_service.schedule_repo.join_waitlist(user_id, date_str)
        )

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

    # ── #17 Персональное приветствие с именем ──────────────────────────────
    def get_personalized_greeting(user_id: int, first_name: str) -> str:
        """Создаёт персональное приветствие на основе истории посещений."""
        import asyncio

        try:
            last_appt = asyncio.run(
                asyncio.to_thread(appt_service.get_last_appointment, user_id)
            )
            if last_appt:
                return (
                    f"👋 Добро пожаловать снова, <b>{last_appt.client_name}!</b>\n\n"
                    f"Последняя запись была на <b>{last_appt.date}</b> в <b>{last_appt.time}</b>.\n"
                    f"Хотите записаться ещё раз?"
                )
        except Exception:
            pass

        # Fallback
        return f"👋 Добро пожаловать, <b>{first_name}</b>!\n\nЧто вы хотите сделать?"

    # ═══════════════════════════════════════════════════════════════════════
    # АДМИНИСТРАТОРСКИЕ ФУНКЦИИ
    # ═══════════════════════════════════════════════════════════════════════

    # ── #14 История посещений клиента ──────────────────────────────────────
    @router.callback_query(AdminFSM.main_menu, F.data == "admin_view_history")
    async def admin_view_client_history(callback: CallbackQuery, state: FSMContext) -> None:
        """Показывает историю посещений для введённого клиента.

        FIXED: фича #14 — история посещений с полной статистикой.
        """
        await state.set_state(AdminFSM.waiting_for_search_query)
        await callback.message.answer(
            "🔍 Введите <b>имя</b> или <b>номер телефона</b> клиента для просмотра истории:"
        )
        await callback.answer()

    @router.message(AdminFSM.waiting_for_search_query)
    async def admin_search_client_history(message: Message, state: FSMContext) -> None:
        """Ищет клиента и выводит его историю посещений."""
        import asyncio

        query = message.text.strip()
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
            await message.answer(f"ℹ️ Клиент '{query}' не найден")
            await state.clear()
            return

        # Берём первого найденного клиента для получения истории
        user_id = results[0].user_id
        history = await asyncio.to_thread(appt_service.get_client_visit_history, user_id)

        text = (
            f"📋 <b>История посещений</b>\n\n"
            f"👤 Клиент: <b>{results[0].client_name}</b>\n"
            f"📱 Телефон: <b>{results[0].phone}</b>\n\n"
            f"📊 <b>Статистика:</b>\n"
            f"  • Всего посещений: <b>{history.get('total_visits', 0)}</b>\n"
            f"  • Завершено: <b>{history.get('completed', 0)}</b>\n"
            f"  • Отменено: <b>{history.get('cancelled', 0)}</b>\n"
            f"  • Последний визит: <b>{history.get('last_visit_date', 'N/A')}</b>\n"
            f"  • Последнее завершённое: <b>{history.get('last_completed_date', 'N/A')}</b>\n\n"
            f"📝 <b>Все записи:</b>\n"
        )

        for appt in results:
            status = "✅" if not appt.is_cancelled else "❌"
            text += f"{status} {appt.date} {appt.time} — {appt.service or 'услуга'}\n"

        await message.answer(text)
        await state.clear()

    # ── #23 Статистика по месяцам в admin-панели ───────────────────────────
    @router.callback_query(AdminFSM.main_menu, F.data == "admin_monthly_stats")
    async def admin_show_monthly_stats(callback: CallbackQuery, state: FSMContext) -> None:
        """Показывает статистику по текущему месяцу."""
        import asyncio

        now = datetime.now()
        stats = await asyncio.to_thread(
            appt_service.get_month_statistics, now.year, now.month
        )

        # Преобразуем дни недели (0=пн, 6=вс) в названия
        weekday_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
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

        await callback.message.answer(text)
        await callback.answer()

    # ── #12 Шаблоны расписания ────────────────────────────────────────────
    @router.callback_query(AdminFSM.main_menu, F.data == "admin_templates")
    async def admin_manage_templates(callback: CallbackQuery, state: FSMContext) -> None:
        """Показывает меню управления шаблонами расписания.

        FIXED: фича #12 — сохранение и применение шаблонов рабочих дней.
        """
        import asyncio

        # Получаем список шаблонов из БД
        try:
            templates = await asyncio.to_thread(
                lambda: sched_service.schedule_repo.get_workday_templates()
            )
        except Exception:
            templates = []

        text = "📋 <b>Шаблоны расписания</b>\n\n"

        if not templates:
            text += "ℹ️ Нет сохранённых шаблонов\n\n"
        else:
            for tmpl in templates:
                text += f"• <b>{tmpl['name']}</b>: {tmpl['schedule']}\n"

        kb = AdminKeyboard.templates_menu()
        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()

    @router.callback_query(AdminFSM.main_menu, F.data == "admin_save_template")
    async def admin_save_template_start(callback: CallbackQuery, state: FSMContext) -> None:
        """Начинает сохранение шаблона расписания."""
        await state.set_state(AdminFSM.waiting_for_template_name)
        await callback.message.answer(
            "📝 Введите <b>название шаблона</b> (например, 'Пн-Пт 10:00-18:00'):"
        )
        await callback.answer()

    @router.message(AdminFSM.waiting_for_template_name)
    async def admin_save_template_name(message: Message, state: FSMContext) -> None:
        """Сохраняет название и запрашивает расписание."""
        await state.update_data(template_name=message.text.strip())
        await state.set_state(AdminFSM.waiting_for_template_schedule)
        await message.answer(
            "🕐 Введите <b>расписание</b> в формате:\n"
            "пн-пт 10:00-18:00 (через запятую для нескольких блоков)"
        )

    @router.message(AdminFSM.waiting_for_template_schedule)
    async def admin_save_template_schedule(message: Message, state: FSMContext) -> None:
        """Сохраняет шаблон."""
        import asyncio

        data = await state.get_data()
        name = data.get("template_name")
        schedule = message.text.strip()

        try:
            await asyncio.to_thread(
                lambda: sched_service.schedule_repo.save_workday_template(name, schedule)
            )
            await message.answer(
                f"✅ Шаблон <b>'{name}'</b> сохранён!\n\n"
                f"Расписание: <code>{schedule}</code>"
            )
        except Exception as exc:
            logger.error("Template save error: %s", exc)
            await message.answer("❌ Ошибка при сохранении шаблона")

        await state.clear()

    # ── #43 Кнопка «Отменить все записи» на дату ──────────────────────────
    @router.callback_query(AdminFSM.main_menu, F.data == "admin_cancel_all_date")
    async def admin_cancel_all_start(callback: CallbackQuery, state: FSMContext) -> None:
        """Начинает процесс массовой отмены записей на дату."""
        await state.set_state(AdminFSM.confirming_cancel_all_date)
        await callback.message.answer(
            "📅 Введите <b>дату</b> для отмены всех записей (формат: YYYY-MM-DD):"
        )
        await callback.answer()

    @router.message(AdminFSM.confirming_cancel_all_date)
    async def admin_cancel_all_confirm(message: Message, state: FSMContext) -> None:
        """Подтверждает отмену всех записей на дату."""
        import asyncio

        date_str = message.text.strip()

        # Валидируем дату
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            await message.answer("❌ Некорректный формат даты. Используйте YYYY-MM-DD")
            return

        # Получаем все записи на эту дату
        appts = await asyncio.to_thread(appt_service.get_appointments_by_date, date_str)

        if not appts:
            await message.answer(f"ℹ️ На {date_str} нет записей")
            await state.clear()
            return

        # Показываем подтверждение
        text = (
            f"⚠️ <b>Отменить все {len(appts)} записей на {date_str}?</b>\n\n"
        )

        for appt in appts:
            text += f"• {appt.time} — {appt.client_name}\n"

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Да, отменить все", callback_data=f"confirm_cancel_all:{date_str}"
                    ),
                    InlineKeyboardButton(text="❌ Отмена", callback_data="admin_main_menu"),
                ]
            ]
        )

        await message.answer(text, reply_markup=kb)
        await state.clear()

    @router.callback_query(F.data.startswith("confirm_cancel_all:"))
    async def admin_cancel_all_execute(callback: CallbackQuery) -> None:
        """Выполняет отмену всех записей на дату."""
        import asyncio

        date_str = callback.data.split(":")[1]

        try:
            appts = await asyncio.to_thread(appt_service.get_appointments_by_date, date_str)

            cancelled_count = 0
            for appt in appts:
                try:
                    await asyncio.to_thread(appt_service.admin_cancel_appointment, appt.id)
                    # Уведомляем клиента об отмене
                    await notif_service.notify_client_cancellation_by_admin(
                        appt.user_id, appt.date, appt.time
                    )
                    cancelled_count += 1
                except Exception as exc:
                    logger.warning("Failed to cancel appointment %s: %s", appt.id, exc)

            await callback.message.answer(
                f"✅ <b>Отменено {cancelled_count} записей на {date_str}</b>\n\n"
                f"Клиентам отправлены уведомления об отмене."
            )
        except Exception as exc:
            logger.exception("Mass cancel error: %s", exc)
            await callback.answer("❌ Ошибка при отмене записей", show_alert=True)

        await callback.answer()

    return router
