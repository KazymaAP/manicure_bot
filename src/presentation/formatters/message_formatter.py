# src/presentation/formatters/message_formatter.py
"""Форматирование сообщений для пользователей и администратора."""

from datetime import datetime, date
from typing import Optional

from src.domain.models.appointment import Appointment
from src.domain.models.time_slot import TimeSlot
from src.domain.models.working_day import WorkingDay
from src.domain.enums.appointment_status import AppointmentStatus
from src.presentation.constants import MONTHS_RU, MONTHS_RU_GEN, WEEKDAYS_RU


class MessageFormatter:
    """Все текстовые шаблоны приложения."""

    # ── Общие ────────────────────────────────────────────────────────────

    @staticmethod
    def welcome(username: Optional[str]) -> str:
        name = f"@{username}" if username else "дорогой гость"
        return (
            f"👋 Привет, {name}!\n\n"
            "💅 Я помогу вам записаться на маникюр.\n\n"
            "Выберите действие в меню ниже:"
        )

    @staticmethod
    def help_text() -> str:
        return (
            "ℹ️ <b>Справка</b>\n\n"
            "📌 <b>Мои записи</b> — посмотреть ваши активные записи\n"
            "📅 <b>Записаться</b> — забронировать новое время\n\n"
            "Если возникли вопросы — пишите администратору."
        )

    @staticmethod
    def error_subscription_required(channel: str) -> str:
        return (
            "⛔ <b>Требуется подписка</b>\n\n"
            f"Для использования бота необходимо подписаться на канал {channel}.\n"
            "После подписки отправьте команду /start"
        )

    @staticmethod
    def error_general() -> str:
        return "❌ Произошла ошибка. Пожалуйста, попробуйте позже."

    # ── Запись клиента ────────────────────────────────────────────────────

    @staticmethod
    def choose_date() -> str:
        return "📅 Выберите удобную дату:"

    @staticmethod
    def choose_time() -> str:
        return "🕐 Выберите удобное время:"

    @staticmethod
    def enter_name() -> str:
        return "✍️ Введите ваше <b>имя</b>:"

    @staticmethod
    def enter_phone() -> str:
        return (
            "📱 Введите ваш <b>номер телефона</b>:\n"
            "<i>Например: +7 999 123-45-67</i>"
        )

    @staticmethod
    def enter_comment() -> str:
        return (
            "💬 Добавьте <b>комментарий</b> к записи\n"
            "<i>(или нажмите «Пропустить»)</i>"
        )

    @staticmethod
    def invalid_name() -> str:
        return "⚠️ Имя должно содержать от 2 до 100 символов. Попробуйте ещё раз:"

    @staticmethod
    def invalid_phone() -> str:
        return "⚠️ Введите корректный номер телефона (минимум 7 цифр). Например: +7 999 123-45-67"

    @staticmethod
    def invalid_appointment_id() -> str:
        return "⚠️ Введите числовой ID записи (например: 42)."

    @staticmethod
    def booking_confirmation(
        date_str: str,
        time_str: str,
        client_name: str,
        phone: str,
        comment: Optional[str],
    ) -> str:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        formatted_date = f"{d.day} {MONTHS_RU_GEN[d.month]} {d.year}"
        comment_line = f"\n💬 Комментарий: {comment}" if comment else ""
        return (
            "📋 <b>Подтвердите запись:</b>\n\n"
            f"📅 Дата: <b>{formatted_date}</b>\n"
            f"🕐 Время: <b>{time_str}</b>\n"
            f"👤 Имя: <b>{client_name}</b>\n"
            f"📱 Телефон: <b>{phone}</b>"
            f"{comment_line}\n\n"
            "Всё верно?"
        )

    @staticmethod
    def booking_success(date_str: str, time_str: str, hours_before: int = 24) -> str:
        """Сообщение об успешном бронировании.

        Args:
            date_str: Дата записи «YYYY-MM-DD».
            time_str: Время записи «HH:MM».
            hours_before: За сколько часов придёт напоминание.
        """
        d = datetime.strptime(date_str, "%Y-%m-%d")
        formatted_date = f"{d.day} {MONTHS_RU_GEN[d.month]} {d.year}"
        return (
            "✅ <b>Запись подтверждена!</b>\n\n"
            f"📅 {formatted_date} в {time_str}\n\n"
            f"Ждём вас! За {hours_before} ч до визита придёт напоминание. 💅"
        )

    @staticmethod
    def booking_cancelled_by_user() -> str:
        return "❌ Запись отменена. Возвращаю в главное меню."

    @staticmethod
    def no_available_slots() -> str:
        return (
            "😔 На выбранную дату нет свободных слотов.\n"
            "Пожалуйста, выберите другую дату."
        )

    @staticmethod
    def no_available_dates() -> str:
        return (
            "😔 К сожалению, в ближайшее время нет доступных дат.\n"
            "Попробуйте позже или свяжитесь с администратором."
        )

    @staticmethod
    def slot_already_taken() -> str:
        return (
            "⚠️ Это время уже занято.\n"
            "Пожалуйста, выберите другой слот."
        )

    @staticmethod
    def max_appointments_reached(max_count: int) -> str:
        return (
            f"⚠️ У вас уже есть {max_count} активных записей.\n"
            "Для новой записи сначала отмените одну из существующих."
        )

    # ── Мои записи ───────────────────────────────────────────────────────

    @staticmethod
    def my_appointments_empty() -> str:
        return "📭 У вас пока нет активных записей."

    @staticmethod
    def my_appointments_list(appointments: list[Appointment]) -> str:
        lines = ["📋 <b>Ваши записи:</b>\n"]
        for i, appt in enumerate(appointments, start=1):
            d = datetime.strptime(appt.date, "%Y-%m-%d")
            formatted_date = f"{d.day} {MONTHS_RU_GEN[d.month]} {d.year}"
            comment = f"\n   💬 {appt.comment}" if appt.comment else ""
            lines.append(
                f"{i}. 📅 <b>{formatted_date}</b> в <b>{appt.time}</b>"
                f"{comment}"
            )
        return "\n".join(lines)

    @staticmethod
    def appointment_cancel_success() -> str:
        return "✅ Ваша запись отменена."

    @staticmethod
    def appointment_not_found() -> str:
        return "⚠️ Запись не найдена или уже отменена."

    # ── Напоминание ───────────────────────────────────────────────────────

    @staticmethod
    def reminder(date_str: str, time_str: str) -> str:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        formatted_date = f"{d.day} {MONTHS_RU_GEN[d.month]} {d.year}"
        return (
            "⏰ <b>Напоминание о записи</b>\n\n"
            f"Завтра вы записаны на маникюр:\n"
            f"📅 {formatted_date} в <b>{time_str}</b>\n\n"
            "Ждём вас! 💅"
        )

    # ── Администратор: общее ──────────────────────────────────────────────

    @staticmethod
    def admin_welcome() -> str:
        return (
            "🔑 <b>Панель администратора</b>\n\n"
            "Выберите действие:"
        )

    @staticmethod
    def admin_not_authorized() -> str:
        return "⛔ У вас нет прав администратора."

    # ── Администратор: записи ─────────────────────────────────────────────

    @staticmethod
    def admin_appointments_empty() -> str:
        return "📭 Записей нет."

    @staticmethod
    def admin_appointments_list(appointments: list[Appointment], filter_name: str = "все") -> str:
        lines = [f"📋 <b>Записи ({filter_name}):</b>\n"]
        for appt in appointments:
            d = datetime.strptime(appt.date, "%Y-%m-%d")
            formatted_date = f"{d.day} {MONTHS_RU_GEN[d.month]}"
            status_icon = "✅" if appt.is_active else "❌"
            comment = f" | {appt.comment}" if appt.comment else ""
            appt_id_display = f"{appt.id}" if appt.id is not None else "?"
            lines.append(
                f"{status_icon} #{appt_id_display} — {formatted_date} {appt.time} "
                f"| {appt.client_name} {appt.phone}{comment}"
            )
        return "\n".join(lines)

    @staticmethod
    def admin_appointment_detail(appt: Appointment) -> str:
        d = datetime.strptime(appt.date, "%Y-%m-%d")
        formatted_date = f"{d.day} {MONTHS_RU_GEN[d.month]} {d.year}"
        status = "✅ Активна" if appt.is_active else "❌ Отменена"
        comment = f"\n💬 Комментарий: {appt.comment}" if appt.comment else ""
        appt_id_display = f"{appt.id}" if appt.id is not None else "?"
        return (
            f"📋 <b>Запись #{appt_id_display}</b>\n\n"
            f"📅 Дата: {formatted_date}\n"
            f"🕐 Время: {appt.time}\n"
            f"👤 Клиент: {appt.client_name}\n"
            f"📱 Телефон: {appt.phone}\n"
            f"📊 Статус: {status}"
            f"{comment}"
        )

    @staticmethod
    def admin_cancel_success(appointment_id: int, client_name: str) -> str:
        return f"✅ Запись #{appointment_id} клиента {client_name} отменена."

    # ── Администратор: расписание ─────────────────────────────────────────

    @staticmethod
    def admin_schedule_empty() -> str:
        return "📭 Расписание не настроено."

    @staticmethod
    def admin_day_schedule(date_str: str, slots: list[TimeSlot]) -> str:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        formatted_date = f"{d.day} {MONTHS_RU_GEN[d.month]} {d.year}"
        if not slots:
            return f"📅 <b>{formatted_date}</b>\n\n❌ Слотов нет."
        slot_lines = [f"  🕐 {s.time}" for s in slots]
        return (
            f"📅 <b>{formatted_date}</b>\n\n"
            "Доступные слоты:\n" + "\n".join(slot_lines)
        )

    @staticmethod
    def admin_slot_added(date_str: str, time_str: str) -> str:
        return f"✅ Слот <b>{time_str}</b> добавлен на {date_str}."

    @staticmethod
    def admin_slot_deleted(date_str: str, time_str: str) -> str:
        return f"✅ Слот <b>{time_str}</b> удалён с {date_str}."

    @staticmethod
    def admin_slot_already_exists() -> str:
        return "⚠️ Такой слот уже существует."

    @staticmethod
    def admin_day_opened(date_str: str) -> str:
        return f"✅ День <b>{date_str}</b> открыт для записи."

    @staticmethod
    def admin_day_closed(date_str: str) -> str:
        return f"🔒 День <b>{date_str}</b> закрыт для записи."

    @staticmethod
    def admin_enter_slot_time() -> str:
        return (
            "⏰ Введите время нового слота в формате <b>ЧЧ:ММ</b>\n"
            "<i>Например: 10:00</i>"
        )

    @staticmethod
    def admin_enter_date() -> str:
        return (
            "📅 Введите дату в формате <b>ГГГГ-ММ-ДД</b>\n"
            "<i>Например: 2025-07-15</i>"
        )

    @staticmethod
    def admin_invalid_time_format() -> str:
        return "❌ Неверный формат времени. Введите в формате ЧЧ:ММ (например, 10:00)."

    @staticmethod
    def admin_invalid_date_format() -> str:
        return "❌ Неверный формат даты. Введите в формате ГГГГ-ММ-ДД."

    # ── Администратор: статистика ─────────────────────────────────────────

    @staticmethod
    def admin_stats(
        total: int,
        confirmed: int,
        cancelled: int,
        today: int,
        week: int,
    ) -> str:
        return (
            "📊 <b>Статистика</b>\n\n"
            f"📋 Всего записей: <b>{total}</b>\n"
            f"✅ Подтверждено: <b>{confirmed}</b>\n"
            f"❌ Отменено: <b>{cancelled}</b>\n\n"
            f"📅 Сегодня: <b>{today}</b>\n"
            f"📆 За неделю: <b>{week}</b>"
        )

    @staticmethod
    def operation_cancelled() -> str:
        return "❌ Операция отменена."

    # ── Уведомления (для notification_service) ───────────────────────────

    @staticmethod
    def notify_admin_new_booking(
        client_name: str, phone: str, date: str, time: str,
        appt_id: int | None, username: str | None, user_id: int,
    ) -> str:
        uname = f"@{username}" if username else "—"
        appt_display = f"#{appt_id}" if appt_id is not None else "#-"
        return (
            "🌸 <b>Новая запись!</b>\n\n"
            f"👤 Клиент: <b>{client_name}</b>\n"
            f"📞 Телефон: <code>{phone}</code>\n"
            f"📅 Дата: <b>{date}</b>\n"
            f"🕐 Время: <b>{time}</b>\n"
            f"🔖 ID записи: <code>{appt_display}</code>\n"
            f"Telegram: {uname} (ID: <code>{user_id}</code>)"
        )

    @staticmethod
    def notify_admin_cancellation(
        client_name: str, date: str, time: str, phone: str,
    ) -> str:
        return (
            "⚠️ <b>Клиент отменил запись!</b>\n\n"
            f"👤 {client_name}\n"
            f"📅 {date} в {time}\n"
            f"📞 {phone}"
        )

    @staticmethod
    def notify_client_cancellation_by_admin(date: str, time: str, service_name: str = "мастеру") -> str:
        return (
            "⚠️ <b>Ваша запись отменена администратором.</b>\n\n"
            f"📅 {date} в {time}\n\n"
            f"Если есть вопросы — обратитесь к {service_name}."
        )

    @staticmethod
    def send_reminder(time: str, service_name: str = "маникюр") -> str:
        return (
            "💅 <b>Напоминание о записи!</b>\n\n"
            f"Напоминаем, что вы записаны на {service_name} <b>завтра в {time}</b>.\n"
            "Ждём вас! 🌸"
        )

    @staticmethod
    def admin_choose_filter() -> str:
        return "Выберите фильтр:"

    @staticmethod
    def admin_choose_date() -> str:
        return "Выберите дату для управления:"

    @staticmethod
    def main_menu_title() -> str:
        return "Главное меню:"

