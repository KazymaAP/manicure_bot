# src/presentation/formatters/message_formatter.py
"""Форматирование сообщений для пользователей и администратора.

FIXED: теперь использует config.json (через Container loader) если доступно —
возможность кастомизации текстов; при отсутствии значений используются прежние дефолты.
"""

from datetime import datetime
from typing import Any
import html
import os
import json
from functools import lru_cache

from src.domain.models.appointment import Appointment
from src.domain.models.time_slot import TimeSlot
from src.presentation.constants import MONTHS_RU_GEN


def _escape(value: Any) -> str:
    """FIXED BUG-M2: экранирует HTML-спецсимволы в пользовательских данных.

    Предотвращает непредвиденное форматирование в Telegram при parse_mode=HTML.
    Пример: имя '</b>hacked<b>' → '&lt;/b&gt;hacked&lt;b&gt;' (безопасно отображается).
    """
    return html.escape(str(value)) if value is not None else ""


@lru_cache(maxsize=1)
def _load_local_config() -> dict[str, Any]:
    # FIXED: загружаем config.json локально, чтобы избежать циклических импортов между
    # dependencies -> notification_service -> message_formatter
    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config.json")
    try:
        with open(config_path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}


def _cfg() -> dict[str, Any]:
    # Возвращает кэшированный config.json (если есть)
    return _load_local_config() or {}


class MessageFormatter:
    """Все текстовые шаблоны приложения.

    Настраиваемые тексты читаются из config.json при наличии соответствующих ключей.
    """

    @staticmethod
    def _tpl(key: str, default: str, **kwargs) -> str:
        cfg = _cfg()
        parts = key.split(".")
        cur = cfg
        for p in parts:
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            else:
                cur = None
                break
        tpl = cur if isinstance(cur, str) else default
        try:
            return tpl.format(**kwargs)
        except Exception:
            return tpl

    # ── Общие ────────────────────────────────────────────────────────────

    @staticmethod
    def welcome(username: str | None) -> str:
        name = f"@{username}" if username else "дорогой гость"
        default = (
            f"👋 Привет, {name}!\n\n"
            "💅 Я помогу вам записаться на маникюр.\n\n"
            "Выберите действие в меню ниже:"
        )
        return MessageFormatter._tpl("bot.welcome", default, username=username, name=name)

    @staticmethod
    def help_text() -> str:
        default = (
            "ℹ️ <b>Справка</b>\n\n"
            "📌 <b>Мои записи</b> — посмотреть ваши активные записи\n"
            "📅 <b>Записаться</b> — забронировать новое время\n\n"
            "Если возникли вопросы — пишите администратору."
        )
        return MessageFormatter._tpl("bot.help_text", default)

    @staticmethod
    def error_subscription_required(channel: str) -> str:
        default = (
            "⛔ <b>Требуется подписка</b>\n\n"
            f"Для использования бота необходимо подписаться на канал {channel}.\n"
            "После подписки отправьте команду /start"
        )
        return MessageFormatter._tpl("bot.error_subscription_required", default, channel=channel)

    @staticmethod
    def error_general() -> str:
        return MessageFormatter._tpl("bot.error_general", "❌ Произошла ошибка. Пожалуйста, попробуйте позже.")

    # ── Запись клиента ────────────────────────────────────────────────────

    @staticmethod
    def choose_date() -> str:
        return MessageFormatter._tpl("booking.choose_date", "📅 Выберите удобную дату:")

    @staticmethod
    def choose_time() -> str:
        return MessageFormatter._tpl("booking.choose_time", "🕐 Выберите удобное время:")

    @staticmethod
    def enter_name() -> str:
        return MessageFormatter._tpl("booking.enter_name", "✍️ Введите ваше <b>имя</b>:")

    @staticmethod
    def enter_phone() -> str:
        return MessageFormatter._tpl("booking.enter_phone", "📱 Введите ваш <b>номер телефона</b>:\n<i>Например: +7 999 123-45-67</i>")

    @staticmethod
    def enter_comment() -> str:
        return MessageFormatter._tpl("booking.enter_comment", "💬 Добавьте <b>комментарий</b> к записи\n<i>(или нажмите «Пропустить»)</i>")

    @staticmethod
    def invalid_name() -> str:
        return MessageFormatter._tpl("booking.invalid_name", "⚠️ Имя должно содержать от 2 до 100 символов. Попробуйте ещё раз:")

    @staticmethod
    def invalid_phone() -> str:
        return MessageFormatter._tpl("booking.invalid_phone", "⚠️ Введите корректный номер телефона (например: +7 999 123-45-67)")

    @staticmethod
    def invalid_appointment_id() -> str:
        return MessageFormatter._tpl("booking.invalid_appointment_id", "⚠️ Введите числовой ID записи (например: 42).")

    @staticmethod
    def booking_confirmation(
        date_str: str,
        time_str: str,
        client_name: str,
        phone: str,
        comment: str | None,
        service: str | None = None,
    ) -> str:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        formatted_date = f"{d.day} {MONTHS_RU_GEN[d.month]} {d.year}"
        # FIXED BUG-M2: экранируем пользовательские данные перед вставкой в HTML-шаблон
        safe_name = _escape(client_name)
        safe_phone = _escape(phone)
        safe_comment = _escape(comment) if comment else None
        safe_service = _escape(service) if service else None
        comment_line = f"\n💬 Комментарий: {safe_comment}" if safe_comment else ""
        service_line = f"\n💼 Услуга: <b>{safe_service}</b>" if safe_service else ""
        default = (
            "📋 <b>Подтвердите запись:</b>\n\n"
            f"📅 Дата: <b>{formatted_date}</b>\n"
            f"🕐 Время: <b>{time_str}</b>\n"
            f"👤 Имя: <b>{safe_name}</b>\n"
            f"📱 Телефон: <b>{safe_phone}</b>"
            f"{service_line}"
            f"{comment_line}\n\n"
            "Всё верно?"
        )
        return MessageFormatter._tpl("booking.confirmation", default, date=formatted_date, time=time_str, client_name=safe_name, phone=safe_phone, comment=safe_comment, service=safe_service)

    @staticmethod
    def booking_success(date_str: str, time_str: str, hours_before: int = 24) -> str:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        formatted_date = f"{d.day} {MONTHS_RU_GEN[d.month]} {d.year}"
        default = (
            "✅ <b>Запись подтверждена!</b>\n\n"
            f"📅 {formatted_date} в {time_str}\n\n"
            f"Ждём вас! За {hours_before} ч до визита придёт напоминание. 💅"
        )
        return MessageFormatter._tpl("booking.success", default, date=formatted_date, time=time_str, hours_before=hours_before)

    @staticmethod
    def booking_cancelled_by_user() -> str:
        return MessageFormatter._tpl("booking.cancelled", "❌ Запись отменена. Возвращаю в главное меню.")

    @staticmethod
    def no_available_slots() -> str:
        return MessageFormatter._tpl("booking.no_slots", "😔 На выбранную дату нет свободных слотов.\nПожалуйста, выберите другую дату.")

    @staticmethod
    def no_available_dates() -> str:
        return MessageFormatter._tpl("booking.no_dates", "😔 К сожалению, в ближайшее время нет доступных дат.\nПопробуйте позже или свяжитесь с администратором.")

    @staticmethod
    def slot_already_taken() -> str:
        return MessageFormatter._tpl("booking.slot_taken", "⚠️ Это время уже занято.\nПожалуйста, выберите другой слот.")

    @staticmethod
    def max_appointments_reached(max_count: int) -> str:
        return MessageFormatter._tpl("booking.max_reached", f"⚠️ У вас уже есть {max_count} активных записей.\nДля новой записи сначала отмените одну из существующих.", max_count=max_count)

    # ── Мои записи ───────────────────────────────────────────────────────

    @staticmethod
    def my_appointments_empty() -> str:
        return MessageFormatter._tpl("my.empty", "📭 У вас пока нет активных записей.")

    @staticmethod
    def my_appointments_list(appointments: list[Appointment]) -> str:
        lines = [MessageFormatter._tpl("my.header", "📋 <b>Ваши записи:</b>\n")]
        for i, appt in enumerate(appointments, start=1):
            d = datetime.strptime(appt.date, "%Y-%m-%d")
            formatted_date = f"{d.day} {MONTHS_RU_GEN[d.month]} {d.year}"
            comment = f"\n   💬 {appt.comment}" if appt.comment else ""
            lines.append(
                f"{i}. 📅 <b>{formatted_date}</b> в <b>{appt.time}</b>" + comment
            )
        return "\n".join(lines)

    @staticmethod
    def appointment_cancel_success() -> str:
        return MessageFormatter._tpl("my.cancel_success", "✅ Ваша запись отменена.")

    @staticmethod
    def appointment_not_found() -> str:
        return MessageFormatter._tpl("my.not_found", "⚠️ Запись не найдена или уже отменена.")

    # ── Напоминание ───────────────────────────────────────────────────────

    @staticmethod
    def reminder(date_str: str, time_str: str, hours_before: int = 24) -> str:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        formatted_date = f"{d.day} {MONTHS_RU_GEN[d.month]} {d.year}"
        # FIXED: текст зависит от hours_before — не захардкожено "завтра"
        default = (
            "⏰ <b>Напоминание о записи</b>\n\n"
            f"Напоминаем, что вы записаны на маникюр {int(hours_before)} ч до визита:\n"
            f"📅 {formatted_date} в <b>{time_str}</b>\n\n"
            "Ждём вас! 💅"
        )
        return MessageFormatter._tpl("reminder.default", default, date=formatted_date, time=time_str, hours_before=hours_before)

    # ── Администратор: общее ──────────────────────────────────────────────

    @staticmethod
    def admin_welcome() -> str:
        return MessageFormatter._tpl("admin.welcome", "🔑 <b>Панель администратора</b>\n\nВыберите действие:")

    @staticmethod
    def admin_not_authorized() -> str:
        return MessageFormatter._tpl("admin.not_authorized", "⛔ У вас нет прав администратора.")

    # ── Администратор: записи ─────────────────────────────────────────────

    @staticmethod
    def admin_appointments_empty() -> str:
        return MessageFormatter._tpl("admin.appointments_empty", "📭 Записей нет.")

    @staticmethod
    def admin_appointments_list(appointments: list[Appointment], filter_name: str = "все") -> str:
        lines = [MessageFormatter._tpl("admin.appointments_header", f"📋 <b>Записи ({filter_name}):</b>\n")]
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
        # FIXED BUG-M2: экранируем данные клиента перед вставкой в HTML
        safe_name = _escape(appt.client_name)
        safe_phone = _escape(appt.phone)
        safe_comment = _escape(appt.comment) if appt.comment else None
        comment = f"\n💬 Комментарий: {safe_comment}" if safe_comment else ""
        appt_id_display = f"{appt.id}" if appt.id is not None else "?"
        return (
            f"📋 <b>Запись #{appt_id_display}</b>\n\n"
            f"📅 Дата: {formatted_date}\n"
            f"🕐 Время: {appt.time}\n"
            f"👤 Клиент: {safe_name}\n"
            f"📱 Телефон: {safe_phone}\n"
            f"📊 Статус: {status}"
            f"{comment}"
        )

    @staticmethod
    def admin_cancel_success(appointment_id: int, client_name: str) -> str:
        return MessageFormatter._tpl("admin.cancel_success", f"✅ Запись #{appointment_id} клиента {client_name} отменена.", appointment_id=appointment_id, client_name=client_name)

    # ── Администратор: расписание ─────────────────────────────────────────

    @staticmethod
    def admin_schedule_empty() -> str:
        return MessageFormatter._tpl("admin.schedule_empty", "📭 Расписание не настроено.")

    @staticmethod
    def admin_day_schedule(date_str: str, slots: list[TimeSlot]) -> str:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        formatted_date = f"{d.day} {MONTHS_RU_GEN[d.month]} {d.year}"
        if not slots:
            return MessageFormatter._tpl("admin.day_empty", f"📅 <b>{formatted_date}</b>\n\n❌ Слотов нет.")
        slot_lines = [f"  🕐 {s.time}" for s in slots]
        return MessageFormatter._tpl("admin.day_schedule", "", date=formatted_date, slots=slot_lines) or (f"📅 <b>{formatted_date}</b>\n\nДоступные слоты:\n" + "\n".join(slot_lines))

    @staticmethod
    def admin_slot_added(date_str: str, time_str: str) -> str:
        return MessageFormatter._tpl("admin.slot_added", f"✅ Слот <b>{time_str}</b> добавлен на {date_str}.")

    @staticmethod
    def admin_slot_deleted(date_str: str, time_str: str) -> str:
        return MessageFormatter._tpl("admin.slot_deleted", f"✅ Слот <b>{time_str}</b> удалён с {date_str}.")

    @staticmethod
    def admin_slot_already_exists() -> str:
        return MessageFormatter._tpl("admin.slot_exists", "⚠️ Такой слот уже существует.")

    @staticmethod
    def admin_day_opened(date_str: str) -> str:
        return MessageFormatter._tpl("admin.day_opened", f"✅ День <b>{date_str}</b> открыт для записи.")

    @staticmethod
    def admin_day_closed(date_str: str) -> str:
        return MessageFormatter._tpl("admin.day_closed", f"🔒 День <b>{date_str}</b> закрыт для записи.")

    @staticmethod
    def admin_enter_slot_time() -> str:
        return MessageFormatter._tpl("admin.enter_slot_time", "⏰ Введите время нового слота в формате <b>ЧЧ:ММ</b>\n<i>Например: 10:00</i>")

    @staticmethod
    def admin_enter_date() -> str:
        return MessageFormatter._tpl("admin.enter_date", "📅 Введите дату в формате <b>ГГГГ-ММ-ДД</b>\n<i>Например: 2025-07-15</i>")

    @staticmethod
    def admin_invalid_time_format() -> str:
        return MessageFormatter._tpl("admin.invalid_time", "❌ Неверный формат времени. Введите в формате ЧЧ:ММ (например, 10:00).")

    @staticmethod
    def admin_invalid_date_format() -> str:
        return MessageFormatter._tpl("admin.invalid_date", "❌ Неверный формат даты. Введите в формате ГГГГ-ММ-ДД.")

    # ── Администратор: статистика ─────────────────────────────────────────

    @staticmethod
    def admin_stats(
        total: int,
        confirmed: int,
        cancelled: int,
        today: int,
        week: int,
    ) -> str:
        default = (
            "📊 <b>Статистика</b>\n\n"
            f"📋 Всего записей: <b>{total}</b>\n"
            f"✅ Подтверждено: <b>{confirmed}</b>\n"
            f"❌ Отменено: <b>{cancelled}</b>\n\n"
            f"📅 Сегодня: <b>{today}</b>\n"
            f"📆 За неделю: <b>{week}</b>"
        )
        return MessageFormatter._tpl("admin.stats", default, total=total, confirmed=confirmed, cancelled=cancelled, today=today, week=week)

    @staticmethod
    def operation_cancelled() -> str:
        return MessageFormatter._tpl("common.operation_cancelled", "❌ Операция отменена.")

    # ── Уведомления (для notification_service) ───────────────────────────

    @staticmethod
    def notify_admin_new_booking(
        client_name: str, phone: str, date: str, time: str,
        appt_id: int | None, username: str | None, user_id: int,
    ) -> str:
        # FIXED BUG-M2: экранируем данные пользователя
        safe_name = _escape(client_name)
        safe_phone = _escape(phone)
        safe_username = _escape(username) if username else None
        uname = f"@{safe_username}" if safe_username else "—"
        appt_display = f"#{appt_id}" if appt_id is not None else "#-"
        default = (
            "🌸 <b>Новая запись!</b>\n\n"
            f"👤 Клиент: <b>{safe_name}</b>\n"
            f"📞 Телефон: <code>{safe_phone}</code>\n"
            f"📅 Дата: <b>{date}</b>\n"
            f"🕐 Время: <b>{time}</b>\n"
            f"🔖 ID записи: <code>{appt_display}</code>\n"
            f"Telegram: {uname} (ID: <code>{user_id}</code>)"
        )
        return MessageFormatter._tpl("notify.new_booking", default, client_name=safe_name, phone=safe_phone, date=date, time=time, appt_id=appt_id, username=safe_username, user_id=user_id)

    @staticmethod
    def notify_admin_cancellation(
        client_name: str, date: str, time: str, phone: str,
    ) -> str:
        default = (
            "⚠️ <b>Клиент отменил запись!</b>\n\n"
            f"👤 {client_name}\n"
            f"📅 {date} в {time}\n"
            f"📞 {phone}"
        )
        return MessageFormatter._tpl("notify.cancellation", default, client_name=client_name, date=date, time=time, phone=phone)

    @staticmethod
    def notify_client_cancellation_by_admin(date: str, time: str, service_name: str = "мастеру") -> str:
        default = (
            "⚠️ <b>Ваша запись отменена администратором.</b>\n\n"
            f"📅 {date} в {time}\n\n"
            f"Если есть вопросы — обратитесь к {service_name}."
        )
        return MessageFormatter._tpl("notify.client_cancel_by_admin", default, date=date, time=time, service_name=service_name)

    @staticmethod
    # FIXED: сообщение напоминания не должно предполагать слово "завтра" — теперь шаблон нейтральный и зависит от hours_before в ReminderService
    def send_reminder(time: str, service_name: str = "маникюр") -> str:
        default = (
            "💅 <b>Напоминание о записи!</b>\n\n"
            f"Напоминаем, что вы записаны на {service_name} в <b>{time}</b>.\n"
            "Ждём вас! 🌸"
        )
        return MessageFormatter._tpl("notify.reminder", default, time=time, service_name=service_name)

    @staticmethod
    def admin_choose_filter() -> str:
        return MessageFormatter._tpl("admin.choose_filter", "Выберите фильтр:")

    @staticmethod
    def admin_choose_date() -> str:
        return MessageFormatter._tpl("admin.choose_date", "Выберите дату для управления:")

    @staticmethod
    def main_menu_title() -> str:
        return MessageFormatter._tpl("common.main_menu_title", "Главное меню:")

    @staticmethod
    def user_blocked() -> str:
        return MessageFormatter._tpl("booking.user_blocked", "⛔ Вы заблокированы и не можете записываться. Обратитесь к администратору.")

    # ── Новые форматеры для расширенных фич ────────────────────────────────

    @staticmethod
    def slot_duration_with_end(time_str: str, duration_minutes: int) -> str:
        """Форматирует слот с отображением времени окончания.

        FIXED: фича #47 — показывает примерное время завершения услуги.
        """
        try:
            from datetime import datetime, timedelta

            start = datetime.strptime(time_str, "%H:%M")
            end = start + timedelta(minutes=duration_minutes)
            return f"🕐 {start.strftime('%H:%M')} – {end.strftime('%H:%M')} ({duration_minutes} мин)"
        except Exception:
            return f"🕐 {time_str} (~{duration_minutes} мин)"

    @staticmethod
    def nearby_slots_list(slots: list[tuple[str, str]]) -> str:
        """Форматирует список ближайших доступных слотов.

        FIXED: фича #5 — показывает 3-5 ближайших свободных дат.

        Args:
            slots: Список кортежей (date, time).
        """
        text = "📅 <b>Ближайшие свободные слоты:</b>\n\n"
        for i, (date, time) in enumerate(slots[:5], 1):
            text += f"{i}. <b>{date}</b> в <b>{time}</b>\n"
        if len(slots) > 5:
            text += f"\n... и ещё {len(slots) - 5}"
        return text

    @staticmethod
    def waitlist_notification(date: str, time: str) -> str:
        """Сообщение о наличии свободного места в листе ожидания.

        FIXED: фича #7 — уведомление о свободном месте.
        """
        return (
            f"🔔 <b>Свободное место!</b>\n\n"
            f"Появился слот на <b>{date}</b> в <b>{time}</b>.\n"
            f"Нажмите кнопку ниже, чтобы забронировать!"
        )

    @staticmethod
    def transfer_success(old_date: str, old_time: str, new_date: str, new_time: str) -> str:
        """Сообщение об успешном переносе записи.

        FIXED: фича #4 — подтверждение переноса.
        """
        return (
            f"✅ <b>Запись успешно перенесена!</b>\n\n"
            f"Было: <b>{old_date}</b> в <b>{old_time}</b>\n"
            f"Стало: <b>{new_date}</b> в <b>{new_time}</b>"
        )

    @staticmethod
    def remind_24h_before(client_name: str, date: str, time: str, address: str = "") -> str:
        """Напоминание за 24 часа.

        FIXED: фича #16 — первое напоминание за день.
        """
        text = (
            f"📆 Привет, <b>{client_name}!</b>\n\n"
            f"Напоминаем о вашей записи <b>завтра</b> в <b>{time}</b> 🕐\n"
        )
        if address:
            text += f"\n📍 Адрес: <code>{address}</code>\n"
        text += "\nПодтвердите, что вы придёте, или отмените запись."
        return text

    @staticmethod
    def remind_2h_before(client_name: str, date: str, time: str, address: str = "") -> str:
        """Напоминание за 2 часа.

        FIXED: фича #16 — второе напоминание перед визитом.
        """
        text = (
            f"⏰ Напоминаем, <b>{client_name}!</b>\n\n"
            f"Ваша запись через <b>2 часа</b> в <b>{time}</b> 🕐\n"
        )
        if address:
            text += f"\n📍 Адрес: <code>{address}</code>\n"
        return text

    @staticmethod
    def remind_1h_before(client_name: str, date: str, time: str, address: str = "") -> str:
        """Напоминание за 1 час (с адресом).

        FIXED: фича #49 — финальное напоминание с адресом.
        """
        text = (
            f"⚡ Ещё <b>час до вашей записи</b>, <b>{client_name}!</b>\n\n"
            f"Время: <b>{time}</b> 🕐\n"
        )
        if address:
            text += f"📍 Адрес: <code>{address}</code>\n"
        text += "\nПриходите вовремя! 🌸"
        return text

    @staticmethod
    def schedule_view_for_client(dates: list[str], free_slots_per_date: dict) -> str:
        """Показывает расписание для клиентов.

        FIXED: фича #46 — просмотр ближайших открытых дат и количество слотов.
        """
        text = "📆 <b>Открытые даты и количество свободных мест:</b>\n\n"
        for date in dates[:10]:  # Показываем до 10 ближайших дат
            free_count = free_slots_per_date.get(date, 0)
            status = "🟢 Много мест" if free_count > 2 else "🟡 1-2 места" if free_count > 0 else "🔴 Ожидание"
            text += f"<b>{date}</b> — {status} ({free_count})\n"
        return text

    @staticmethod
    def contact_info(phone: str = "", instagram: str = "", address: str = "", maps_link: str = "") -> str:
        """Информация о контактах мастера.

        FIXED: фича #20 — контактная информация с ссылками.
        """
        text = "📞 <b>Контактная информация</b>\n\n"
        if phone:
            text += f"📱 Телефон: <code>{phone}</code>\n"
        if address:
            text += f"📍 Адрес: <code>{address}</code>\n"
        if instagram:
            text += f"📸 Instagram: {instagram}\n"
        if maps_link:
            text += f"🗺 На карте: {maps_link}\n"
        return text

    @staticmethod
    def price_list(services: dict) -> str:
        """Форматирует прайс-лист услуг из config.json.

        FIXED: фича #21 — красивый прайс-лист с категориями.
        """
        text = "💰 <b>Прайс-лист</b>\n\n"
        for service_name, info in services.items():
            if isinstance(info, dict):
                price = info.get("price", "—")
                duration = info.get("duration", 0)
                text += f"<b>{service_name}</b>: {price} руб. ({duration} мин)\n"
            else:
                text += f"<b>{service_name}</b>: {info} руб.\n"
        return text

    @staticmethod
    def insufficient_slots_warning(free_days_remaining: int, days_ahead: int) -> str:
        """Предупреждение администратору об отсутствии слотов.

        FIXED: фича #24 — уведомление администратору при < 3 свободных дней.
        """
        return (
            f"⚠️ <b>ВНИМАНИЕ!</b>\n\n"
            f"В расписании осталось <b>{free_days_remaining}</b> свободных дней "
            f"(из {days_ahead} в горизонте).\n\n"
            f"Пожалуйста, откройте новые даты для бронирования! 📅"
        )

    @staticmethod
    def share_bot_link(bot_username: str) -> str:
        """Готовая ссылка для поделиться ботом.

        FIXED: фича #19 — реферальное распространение.
        """
        link = f"https://t.me/{bot_username}"
        return (
            f"📤 <b>Поделитесь ботом!</b>\n\n"
            f"Ссылка: {link}\n\n"
            f"Расскажите друзьям о нашем боте для записи на услуги! 🌸"
        )

    @staticmethod
    def dark_format_section(title: str, content: str) -> str:
        """Форматирует секцию в тёмном режиме.

        FIXED: фича #48 — красивые структурированные сообщения.
        """
        separator = "━" * 30
        return (
            f"{separator}\n"
            f"<b>{title}</b>\n"
            f"{separator}\n"
            f"{content}"
        )

    @staticmethod
    def welcome_banner(name: str | None) -> str:
        """Красивое баннерное приветствие с эмодзи и блоком "Что я умею".

        FIXED: оформлено как баннер для /start (фича: персональное приветствие и UX).
        """
        display_name = name or "друг"
        separator = "━" * 30
        what_i_can = (
            "💅 Запись на услуги\n"
            "📆 Просмотр расписания\n"
            "🔔 Напоминания\n"
            "📞 Контакты и прайс\n"
        )
        return (
            f"💅 <b>Привет, {display_name}!</b> {separator} \n"
            "<i>Я бот для записи к мастеру маникюра. Быстро, просто, без звонков!</i>\n"
            f"{separator}\n"
            f"🌸 <b>Что я умею:</b>\n{what_i_can}\n"
            "🌸 Выберите действие ниже:"
        )

    # FIXED: карточка записи в рамке из Unicode-символов
    @staticmethod
    def appointment_card_box(date_str: str, time_str: str, client_name: str, phone: str, comment: str | None = None, service: str | None = None) -> str:
        """Создаёт текстовую карточку записи с рамкой и иконками.

        Использует символы ╔╗╚╝║═ для оформления.
        """
        try:
            from datetime import datetime
            d = datetime.strptime(date_str, "%Y-%m-%d")
            formatted_date = f"{d.day} {MONTHS_RU_GEN[d.month]} {d.year}"
        except Exception:
            formatted_date = date_str
        header = "╔" + "═" * 37 + "╗\n"
        footer = "\n╚" + "═" * 37 + "╝"
        service_line = f"\n💼 Услуга: <b>{service}</b>" if service else ""
        comment_line = f"\n💬 {comment}" if comment else ""
        body = (
            f"║ 📅 <b>{formatted_date}</b>\n"
            f"║ 🕐 <b>{time_str}</b>\n"
            f"║ 👤 <b>{client_name}</b>\n"
            f"║ 📱 <code>{phone}</code>"
            f"{service_line}"
            f"{comment_line}"
        )
        prompt = "\n\nВсё верно? Нажмите ✅ Подтвердить"
        return header + body + footer + prompt

    # FIXED: списки записей — каждая запись отдельный блок с кнопкой отмены (текстовая часть)
    @staticmethod
    def my_appointments_list_blocks(appointments: list[Appointment]) -> str:
        lines = [MessageFormatter._tpl("my.header", "📋 <b>Ваши записи:</b>\n")]
        for i, appt in enumerate(appointments, start=1):
            try:
                from datetime import datetime
                d = datetime.strptime(appt.date, "%Y-%m-%d")
                formatted_date = f"{d.day} {MONTHS_RU_GEN[d.month]} {d.year}"
            except Exception:
                formatted_date = appt.date
            status = "✅ Активна" if appt.is_active else "❌ Отменена"
            header = f"╔══ Запись #{appt.id or i} ══╗\n"
            body = (
                f"📅 <b>{formatted_date}</b> в <b>{appt.time}</b> — <b>{status}</b>\n"
                f"👤 {appt.client_name} | 📱 <code>{appt.phone}</code>\n"
            )
            footer = "╚" + "═" * 35 + "╝\n"
            lines.append(header + body + footer)
        return "\n".join(lines)

    # FIXED: Админ-дашборд — сводка дня в заголовке
    @staticmethod
    def admin_dashboard_summary(today: int, free_slots: int, week: int, total: int = 0, confirmed: int = 0) -> str:
        separator = "━" * 30
        return (
            f"⚙️ <b>Панель администратора</b> {separator}\n"
            f"📅 Сегодня: <b>{today}</b> записей  🟢 Свободных слотов: <b>{free_slots}</b>\n"
            f"📊 За неделю: <b>{week}</b> записей  |  Всего: <b>{total}</b>\n"
            f"{separator}\n"
            "Выберите действие:"
        )

    # FIXED: Карточное напоминание с адресом и призывами
    @staticmethod
    def reminder_card(client_name: str, date: str, time: str, address: str = "") -> str:
        separator = "━" * 30
        text = (
            f"⏰ <b>Напоминание о записи!</b> {separator}\n"
            f"Привет, <b>{client_name}</b>!\n"
            f"📅 <b>{date}</b>  🕐 <b>{time}</b>\n"
        )
        if address:
            text += f"📍 <code>{address}</code>\n"
        text += "\nНажмите кнопку ниже:"
        return text

    # FIXED: праздничное сообщение при успешной записи
    @staticmethod
    def booking_success_festive(date_str: str, time_str: str, service: str | None = None, hours_before: int = 24) -> str:
        try:
            from datetime import datetime
            d = datetime.strptime(date_str, "%Y-%m-%d")
            formatted_date = f"{d.day} {MONTHS_RU_GEN[d.month]} {d.year}"
        except Exception:
            formatted_date = date_str
        service_line = f"\n💅 <b>{service}</b>" if service else ""
        return (
            "🎉 <b>Запись подтверждена!</b>\n\n"
            f"Вы записаны на: 📅 <b>{formatted_date}</b>  🕐 <b>{time_str}</b>{service_line}\n\n"
            f"⏰ Напоминание придёт за {hours_before} ч. До встречи! 🌸"
        )

    # FIXED: прогресс бары для статистики админа
    @staticmethod
    def admin_stats_with_bars(done: int, cancelled: int, total: int) -> str:
        def bar(value: int, total_v: int, width: int = 10) -> str:
            import math
            filled = int(math.ceil(width * (value / total_v))) if total_v else 0
            return "█" * filled + "░" * (width - filled)
        done_pct = int((done / total) * 100) if total else 0
        canceled_pct = int((cancelled / total) * 100) if total else 0
        return (
            f"📊 <b>Статистика</b>\n\n"
            f"✅ Выполнено: <b>{done}</b> {bar(done, total)} {done_pct}%\n"
            f"❌ Отменено: <b>{cancelled}</b> {bar(cancelled, total)} {canceled_pct}%\n"
        )

    # FIXED: формирование локализованной метки слота с длительностью и статусом
    @staticmethod
    def slot_button_label(time_str: str, duration_minutes: int, locked: bool = False) -> str:
        if locked:
            return f"🔒 {time_str} — занято"
        return f"⚡ {time_str} ({duration_minutes} мин)"

    # FIXED: улучшенная ошибка с кнопками действий
    @staticmethod
    def error_with_retry(reason: str | None = None) -> str:
        text = "⚠️ <b>Что-то пошло не так</b>\n\n"
        if reason:
            text += f"{reason}\n\n"
        text += "Попробуйте ещё раз или вернитесь в главное меню."
        return text

