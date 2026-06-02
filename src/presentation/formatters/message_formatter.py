"""
src/presentation/formatters/message_formatter.py — Форматирование сообщений.

Обновлён: тёплый стиль, новые методы для клиентов и расширенной админ-панели.
Все тексты читаются из config.json при наличии, иначе используются встроенные значения.
"""

import html
import json
import os
from datetime import datetime
from functools import lru_cache
from typing import Any

from src.domain.models.appointment import Appointment
from src.domain.models.time_slot import TimeSlot
from src.presentation.constants import MONTHS_RU_GEN


def _escape(value: Any) -> str:
    """Экранирует HTML-спецсимволы в пользовательских данных."""
    return html.escape(str(value)) if value is not None else ""


@lru_cache(maxsize=1)
def _load_local_config() -> dict[str, Any]:
    """Загружает и кэширует config.json."""
    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config.json")
    try:
        with open(config_path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}


def _cfg() -> dict[str, Any]:
    return _load_local_config() or {}


def _fmt_date(date_str: str) -> str:
    """Форматирует дату YYYY-MM-DD в читаемый вид: 'д МесяцГен ГГГГ'."""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{d.day} {MONTHS_RU_GEN[d.month]} {d.year}"
    except Exception:
        return date_str


class MessageFormatter:
    """Все текстовые шаблоны приложения."""

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
        name = username or "дорогой гость"
        default = (
            f"Привет, {name}! 🌸\n\n"
            "Я — Анастасия, мастер маникюра.\n"
            "Здесь ты можешь записаться ко мне в удобное время — всё просто и быстро 💅\n\n"
            "Выбери, что тебя интересует:"
        )
        return MessageFormatter._tpl("bot.welcome", default, name=name)

    @staticmethod
    def welcome_banner(name: str) -> str:
        """Тёплое приветственное баннерное сообщение."""
        cfg = _cfg()
        master_name = cfg.get("master", {}).get("name", "Анастасия")
        default = (
            f"Привет, {_escape(name)}! 🌸\n\n"
            f"Я — {master_name}, мастер маникюра.\n"
            "Здесь ты можешь записаться ко мне в удобное время — всё просто и быстро 💅\n\n"
            "Выбери, что тебя интересует:"
        )
        return MessageFormatter._tpl("bot.welcome", default, name=_escape(name))

    @staticmethod
    def after_visit_thank_you(name: str) -> str:
        """Сообщение после визита — благодарность и предложение записаться снова."""
        cfg = _cfg()
        text = cfg.get("master", {}).get(
            "after_visit_text",
            f"Спасибо, что была у меня, {_escape(name)}! 🌷\n\n"
            "Надеюсь, тебе всё понравилось. Буду рада видеть тебя снова!\n"
            "Если хочешь — запишись уже сейчас 😊"
        )
        try:
            return text.format(name=_escape(name))
        except Exception:
            return text

    @staticmethod
    def help_text() -> str:
        default = (
            "ℹ️ <b>Справка</b>\n\n"
            "📅 <b>Записаться</b> — выбрать услугу, дату и время\n"
            "📋 <b>Мои записи</b> — посмотреть ваши активные записи\n"
            "💰 <b>Цены</b> — прайс на услуги\n"
            "📞 <b>Связаться с мастером</b> — написать напрямую\n\n"
            "Если что-то не получается — просто напишите сюда 🌸"
        )
        return MessageFormatter._tpl("bot.help_text", default)

    @staticmethod
    def error_subscription_required(channel: str) -> str:
        default = (
            "⛔ <b>Требуется подписка</b>\n\n"
            f"Для использования бота необходимо подписаться на канал {channel}.\n"
            "После подписки нажмите «✅ Я подписалась»"
        )
        return MessageFormatter._tpl("bot.error_subscription_required", default, channel=channel)

    @staticmethod
    def error_general() -> str:
        return "❌ Что-то пошло не так. Попробуйте позже или напишите мастеру 🌸"

    @staticmethod
    def main_menu_title() -> str:
        return "Главное меню 🌸"

    # ── Запись клиента ────────────────────────────────────────────────────

    @staticmethod
    def choose_service() -> str:
        return MessageFormatter._tpl(
            "booking.choose_service",
            "💅 Что будем делать?\n\nВыберите услугу:"
        )

    @staticmethod
    def service_card(name: str, price: int | None, duration: int | None, emoji: str = "💅") -> str:
        """Карточка услуги с названием, ценой и длительностью."""
        parts = [f"{emoji} <b>{_escape(name)}</b>"]
        if price is not None:
            parts.append(f"💰 {price} ₽")
        if duration is not None:
            parts.append(f"⏱ {duration} мин")
        return "  |  ".join(parts)

    @staticmethod
    def choose_date() -> str:
        return MessageFormatter._tpl(
            "booking.choose_date",
            "📅 Выберите удобную дату:\n\n<i>Доступные дни выделены в календаре</i>"
        )

    @staticmethod
    def choose_time() -> str:
        return MessageFormatter._tpl("booking.choose_time", "🕐 Выберите удобное время:")

    @staticmethod
    def enter_name() -> str:
        return MessageFormatter._tpl(
            "booking.enter_name",
            "✍️ Как вас зовут?\n\n<i>Введите ваше имя:</i>"
        )

    @staticmethod
    def enter_phone() -> str:
        return MessageFormatter._tpl(
            "booking.enter_phone",
            "📱 Ваш номер телефона?\n\n<i>Например: +7 999 123-45-67</i>"
        )

    @staticmethod
    def enter_comment() -> str:
        return MessageFormatter._tpl(
            "booking.enter_comment",
            "💬 Хотите что-то добавить?\n\n<i>Напишите комментарий или нажмите «Пропустить»</i>"
        )

    @staticmethod
    def invalid_name() -> str:
        return "⚠️ Имя должно содержать от 2 до 100 символов. Попробуйте ещё раз:"

    @staticmethod
    def invalid_phone() -> str:
        return "⚠️ Введите корректный номер телефона\n<i>Например: +7 999 123-45-67</i>"

    @staticmethod
    def invalid_appointment_id() -> str:
        return "⚠️ Введите числовой ID записи (например: 42)."

    @staticmethod
    def booking_confirmation(
        date_str: str,
        time_str: str,
        client_name: str,
        phone: str,
        comment: str | None,
        service: str | None = None,
    ) -> str:
        formatted_date = _fmt_date(date_str)
        safe_name = _escape(client_name)
        safe_phone = _escape(phone)
        safe_comment = _escape(comment) if comment else None
        safe_service = _escape(service) if service else None
        comment_line = f"\n💬 <i>{safe_comment}</i>" if safe_comment else ""
        service_line = f"\n✨ {safe_service}" if safe_service else ""
        return (
            "📋 <b>Проверьте данные записи:</b>\n"
            "─────────────────\n"
            f"📅 <b>{formatted_date}</b>\n"
            f"🕐 <b>{time_str}</b>\n"
            f"👤 {safe_name}\n"
            f"📱 {safe_phone}"
            f"{service_line}"
            f"{comment_line}\n"
            "─────────────────\n"
            "Всё верно? 🌸"
        )

    @staticmethod
    def appointment_card_box(
        date_str: str,
        time_str: str,
        client_name: str,
        phone: str,
        comment: str | None,
        service: str | None = None,
    ) -> str:
        """Карточка записи в рамке для подтверждения."""
        return MessageFormatter.booking_confirmation(
            date_str, time_str, client_name, phone, comment, service
        )

    @staticmethod
    def booking_success(date_str: str, time_str: str, hours_before: int = 24, client_name: str = "") -> str:
        formatted_date = _fmt_date(date_str)
        name_part = f"{_escape(client_name)}, жд" if client_name else "Жд"
        default = (
            f"✅ {name_part}у тебя {formatted_date} в {time_str}! 🌸\n\n"
            "Если что-то изменится — напиши сюда :)\n\n"
            f"<i>Напоминание придёт за {hours_before} ч до визита</i>"
        )
        cfg = _cfg()
        tpl = cfg.get("booking", {}).get(
            "success",
            "✅ {name}, жду тебя {date} в {time}! 🌸\n\n"
            "Если что-то изменится — напиши сюда :)\n\n"
            "<i>Напоминание придёт за {hours_before} ч до визита</i>"
        )
        try:
            name_word = _escape(client_name) if client_name else "Отлично"
            return tpl.format(
                name=name_word,
                date=formatted_date,
                time=time_str,
                hours_before=hours_before,
            )
        except Exception:
            return default

    @staticmethod
    def booking_cancelled_by_user() -> str:
        return "Запись отменена. Возвращаемся в главное меню 🌸"

    @staticmethod
    def no_available_slots() -> str:
        return (
            "😔 На выбранную дату нет свободных слотов.\n"
            "Выберите другую дату или запишитесь в лист ожидания — уведомлю, когда появится место!"
        )

    @staticmethod
    def no_available_dates() -> str:
        return (
            "😔 Пока нет доступных дат для записи.\n"
            "Попробуйте позже или напишите мастеру напрямую 🌸"
        )

    @staticmethod
    def slot_already_taken() -> str:
        return "⚠️ Это время уже занято.\nПожалуйста, выберите другой слот 🌸"

    @staticmethod
    def max_appointments_reached(max_count: int) -> str:
        return (
            f"⚠️ У вас уже есть {max_count} активных записей.\n"
            "Для новой записи сначала отмените одну из существующих."
        )

    @staticmethod
    def user_blocked() -> str:
        return "⛔ К сожалению, вы не можете записаться через бот. Свяжитесь с мастером напрямую."

    # ── Мои записи ────────────────────────────────────────────────────────

    @staticmethod
    def my_appointments_empty() -> str:
        return (
            "📭 У тебя пока нет активных записей.\n\n"
            "Нажми «Записаться», чтобы выбрать удобное время 🌸"
        )

    @staticmethod
    def my_appointments_list(appointments: list[Appointment]) -> str:
        lines = ["📋 <b>Ваши записи:</b>\n"]
        for appt in appointments:
            formatted_date = _fmt_date(appt.date)
            service_line = f"\n   ✨ {_escape(appt.service)}" if appt.service else ""
            comment_line = f"\n   💬 {_escape(appt.comment)}" if appt.comment else ""
            lines.append(
                f"📅 <b>{formatted_date}</b> в <b>{appt.time}</b>"
                f"{service_line}"
                f"{comment_line}"
                f"\n   🆔 #{appt.id}"
            )
        return "\n\n".join(lines)

    @staticmethod
    def my_appointments_list_blocks(appointments: list[Appointment]) -> str:
        """Список записей с разделителями — красивый формат."""
        lines = ["📋 <b>Твои записи:</b>\n"]
        for appt in appointments:
            formatted_date = _fmt_date(appt.date)
            service_line = f"✨ {_escape(appt.service)}\n" if appt.service else ""
            comment_line = f"💬 <i>{_escape(appt.comment)}</i>\n" if appt.comment else ""
            lines.append(
                f"─────────────────\n"
                f"📅 <b>{formatted_date}</b>  🕐 <b>{appt.time}</b>\n"
                f"{service_line}"
                f"{comment_line}"
                f"<i>ID: #{appt.id}</i>"
            )
        return "\n".join(lines)

    @staticmethod
    def appointment_cancel_success() -> str:
        return "✅ Запись отменена.\n\nЕсли захочешь снова — буду рада видеть тебя! 🌸"

    @staticmethod
    def appointment_not_found() -> str:
        return "😔 Запись не найдена. Возможно, она уже была отменена."

    # ── Цены ──────────────────────────────────────────────────────────────

    @staticmethod
    def prices_list(services: dict) -> str:
        """Красивый прайс-лист из словаря services."""
        cfg = _cfg()
        title = cfg.get("prices_title", "💅 <b>Прайс-лист</b>\n\n")
        footer = cfg.get("prices_footer", "\n\n<i>По вопросам — нажмите «Связаться с мастером»</i>")

        # Эмодзи для услуг
        service_emojis = {
            "маникюр": "💅", "педикюр": "🦶", "покрытие": "✨",
            "гель": "💎", "наращивание": "🌟", "дизайн": "🎨",
            "удаление": "🧹", "чистка": "🫧", "парафин": "🕯",
        }

        if not services:
            return title + "<i>Прайс-лист не настроен</i>" + footer

        lines = [title]
        for name, info in services.items():
            emoji = "💅"
            for keyword, em in service_emojis.items():
                if keyword in name.lower():
                    emoji = em
                    break
            price = info.get("price")
            duration = info.get("duration")
            price_str = f"  <b>{price} ₽</b>" if price is not None else ""
            dur_str = f"  <i>{duration} мин</i>" if duration is not None else ""
            lines.append(f"{emoji} {_escape(name)}{price_str}{dur_str}")

        lines.append(footer)
        return "\n".join(lines)

    # ── Контакты ──────────────────────────────────────────────────────────

    @staticmethod
    def contacts_text(phone: str | None = None, instagram: str | None = None,
                      address: str | None = None, maps_link: str | None = None,
                      master_username: str | None = None) -> str:
        """Текст контактной информации мастера."""
        cfg = _cfg()
        title = cfg.get("contacts_title", "📞 <b>Связаться с мастером</b>\n\nПишите в любое время! 🌸\n\n")
        lines = [title]
        if master_username:
            lines.append(f"✉️ Telegram: @{_escape(master_username)}")
        if phone:
            lines.append(f"📱 Телефон: {_escape(phone)}")
        if instagram:
            lines.append(f"📸 Instagram: {_escape(instagram)}")
        if address:
            lines.append(f"📍 Адрес: {_escape(address)}")
            if maps_link:
                lines.append(f"🗺 <a href=\"{maps_link}\">Открыть на карте</a>")
        if len(lines) == 1:
            lines.append("<i>Контакты не настроены. Используйте кнопку ниже.</i>")
        return "\n".join(lines)

    # ── Напоминания ───────────────────────────────────────────────────────

    @staticmethod
    def reminder(date_str: str, time_str: str, hours_before: int = 24, service: str | None = None) -> str:
        """Напоминание клиенту перед визитом."""
        formatted_date = _fmt_date(date_str)
        service_line = f"\n✨ {_escape(service)}" if service else ""
        return (
            f"🔔 <b>Напоминание о записи</b>\n\n"
            f"Привет! Напоминаю, что завтра жду тебя 🌸\n\n"
            f"📅 <b>{formatted_date}</b>\n"
            f"🕐 <b>{time_str}</b>"
            f"{service_line}\n\n"
            f"Если планы изменились — нажми кнопку ниже:"
        )

    # ── Расписание (для клиентов) ─────────────────────────────────────────

    @staticmethod
    def schedule_text(slots_by_date: dict[str, list[str]]) -> str:
        """Расписание свободных слотов для клиентов."""
        if not slots_by_date:
            return "😔 Пока нет доступных дат.\nПопробуйте позже или напишите мастеру 🌸"
        lines = ["📅 <b>Ближайшие свободные дни:</b>\n"]
        for date_str, times in list(slots_by_date.items())[:7]:
            formatted_date = _fmt_date(date_str)
            times_str = "  •  ".join(times[:6])
            if len(times) > 6:
                times_str += f"  ... ещё {len(times)-6}"
            lines.append(f"<b>{formatted_date}</b>\n{times_str}")
        return "\n\n".join(lines)

    @staticmethod
    def nearby_slots_list(slots: list[tuple[str, str]]) -> str:
        lines = ["🟢 <b>Ближайшие свободные слоты:</b>\n"]
        for date_str, time_str in slots:
            lines.append(f"📅 {_fmt_date(date_str)}  🕐 {time_str}")
        return "\n".join(lines)

    @staticmethod
    def reminder_card(client_name: str, date: str, time: str, address: str = "") -> str:
        """Карточка напоминания о визите (используется notification_service)."""
        formatted_date = _fmt_date(date)
        address_line = f"\n📍 {_escape(address)}" if address else ""
        return (
            f"🔔 <b>Напоминание о записи</b>\n\n"
            f"Привет, {_escape(client_name)}! Завтра жду тебя 🌸\n\n"
            f"📅 <b>{formatted_date}</b>\n"
            f"🕐 <b>{time}</b>"
            f"{address_line}\n\n"
            f"Если планы изменились — нажми кнопку ниже:"
        )

    @staticmethod
    def remind_2h_before(client_name: str, date: str, time: str, address: str = "") -> str:
        """Напоминание за 2 часа до записи."""
        formatted_date = _fmt_date(date)
        address_line = f"\n📍 {_escape(address)}" if address else ""
        return (
            f"⏰ Совсем скоро!\n\n"
            f"{_escape(client_name)}, через 2 часа жду тебя 🌸\n\n"
            f"📅 <b>{formatted_date}</b>\n"
            f"🕐 <b>{time}</b>"
            f"{address_line}"
        )

    # ── Лист ожидания ────────────────────────────────────────────────────

    @staticmethod
    def waitlist_added(date_str: str) -> str:
        return (
            f"✅ Ты в листе ожидания на {_fmt_date(date_str)}!\n\n"
            "Как только появится свободное место — сразу сообщу 🌸"
        )

    @staticmethod
    def waitlist_slot_available(date_str: str, time_str: str) -> str:
        return (
            f"🎉 Освободился слот!\n\n"
            f"📅 {_fmt_date(date_str)}  🕐 {time_str}\n\n"
            "Хочешь записаться?"
        )

    # ── Административная панель ───────────────────────────────────────────

    @staticmethod
    def admin_welcome() -> str:
        return "⚙️ <b>Панель администратора</b>\n\nВыберите раздел:"

    @staticmethod
    def admin_not_authorized() -> str:
        return "⛔ Доступ запрещён."

    @staticmethod
    def admin_dashboard_summary(today: int, free_slots: int, week: int, total: int, confirmed: int) -> str:
        return (
            "⚙️ <b>Панель администратора</b>\n"
            "━━━━━━━━━━━━━━━━━\n"
            f"📅 Сегодня записей: <b>{today}</b>\n"
            f"🆓 Свободных слотов: <b>{free_slots}</b>\n"
            f"📆 За неделю: <b>{week}</b>\n"
            f"📊 Всего активных: <b>{confirmed}</b>\n"
            "━━━━━━━━━━━━━━━━━\n"
            "Выберите раздел:"
        )

    @staticmethod
    def admin_today_appointments(appointments: list[Appointment]) -> str:
        """Список записей на сегодня для администратора."""
        if not appointments:
            return "📅 <b>Сегодня</b>\n\nЗаписей на сегодня нет.\nВремя отдыхать! 🌸"
        lines = [f"📅 <b>Сегодня — {len(appointments)} записей:</b>\n"]
        for appt in appointments:
            username_line = f" (@{_escape(appt.username)})" if getattr(appt, 'username', None) else ""
            phone_line = f"\n   📱 {_escape(appt.phone)}" if appt.phone else ""
            service_line = f"\n   ✨ {_escape(appt.service)}" if appt.service else ""
            comment_line = f"\n   💬 {_escape(appt.comment)}" if appt.comment else ""
            lines.append(
                f"🕐 <b>{appt.time}</b> — {_escape(appt.client_name)}{username_line}"
                f"{phone_line}"
                f"{service_line}"
                f"{comment_line}"
                f"\n   🆔 #{appt.id}"
            )
        return "\n\n".join(lines)

    @staticmethod
    def admin_appointments_empty() -> str:
        return "📭 Записей не найдено."

    @staticmethod
    def admin_appointments_list(appointments: list[Appointment], filter_name: str = "все") -> str:
        if not appointments:
            return "📭 Нет записей."
        lines = [f"📋 <b>Записи ({filter_name}):</b>\n"]
        for appt in appointments:
            formatted_date = _fmt_date(appt.date)
            service_line = f" · {_escape(appt.service)}" if appt.service else ""
            status = "✅" if not getattr(appt, 'is_cancelled', False) else "❌"
            lines.append(
                f"{status} <b>#{appt.id}</b>  {formatted_date}  {appt.time}\n"
                f"   👤 {_escape(appt.client_name)}{service_line}\n"
                f"   📱 {_escape(appt.phone)}"
            )
        return "\n\n".join(lines)

    @staticmethod
    def admin_appointment_detail(appt: Appointment) -> str:
        formatted_date = _fmt_date(appt.date)
        username_line = f"\n📲 @{_escape(appt.username)}" if getattr(appt, 'username', None) else ""
        service_line = f"\n✨ Услуга: {_escape(appt.service)}" if appt.service else ""
        comment_line = f"\n💬 {_escape(appt.comment)}" if appt.comment else ""
        return (
            f"📋 <b>Запись #{appt.id}</b>\n"
            "─────────────────\n"
            f"👤 {_escape(appt.client_name)}{username_line}\n"
            f"📱 {_escape(appt.phone)}\n"
            f"📅 {formatted_date}  🕐 {appt.time}"
            f"{service_line}"
            f"{comment_line}"
        )

    @staticmethod
    def admin_cancel_success(appointment_id: int, client_name: str) -> str:
        return f"✅ Запись #{appointment_id} ({_escape(client_name)}) отменена. Клиент уведомлён."

    @staticmethod
    def admin_schedule_empty() -> str:
        return "📅 Нет рабочих дней в расписании.\n\nДобавьте дни через «Управление расписанием»."

    @staticmethod
    def admin_choose_date() -> str:
        return "📅 Выберите дату для просмотра слотов:"

    @staticmethod
    def admin_choose_filter() -> str:
        return "📋 Выберите фильтр для записей:"

    @staticmethod
    def admin_day_schedule(date_str: str, slots: list[TimeSlot]) -> str:
        formatted_date = _fmt_date(date_str)
        if not slots:
            return f"📅 <b>{formatted_date}</b>\n\nСлотов нет. Добавьте через кнопку ниже."
        free = [s for s in slots if not s.is_booked]
        booked = [s for s in slots if s.is_booked]
        lines = [f"📅 <b>{formatted_date}</b>\n"]
        lines.append(f"🆓 Свободно: {len(free)}  |  📌 Занято: {len(booked)}\n")
        for slot in sorted(slots, key=lambda s: s.time):
            if slot.is_booked:
                lines.append(f"📌 {slot.time} — занято")
            else:
                lines.append(f"🟢 {slot.time} — свободно")
        return "\n".join(lines)

    @staticmethod
    def admin_slot_added(date_str: str, time_str: str) -> str:
        return f"✅ Слот {time_str} на {_fmt_date(date_str)} добавлен."

    @staticmethod
    def admin_slot_deleted(date_str: str, time_str: str) -> str:
        return f"✅ Слот {time_str} на {_fmt_date(date_str)} удалён."

    @staticmethod
    def admin_slot_already_exists() -> str:
        return "⚠️ Такой слот уже существует или произошла ошибка."

    @staticmethod
    def admin_day_opened(date_str: str) -> str:
        return f"✅ День {_fmt_date(date_str)} открыт для записей."

    @staticmethod
    def admin_day_closed(date_str: str) -> str:
        return f"🔒 День {_fmt_date(date_str)} закрыт для записей."

    @staticmethod
    def admin_enter_slot_time() -> str:
        return "🕐 Введите время слота в формате <b>ЧЧ:ММ</b>\n<i>Например: 14:30</i>"

    @staticmethod
    def admin_enter_date() -> str:
        return "📅 Введите дату в формате <b>ГГГГ-ММ-ДД</b>\n<i>Например: 2025-06-15</i>"

    @staticmethod
    def admin_invalid_time_format() -> str:
        return "⚠️ Некорректный формат времени. Введите в формате ЧЧ:ММ (например: 14:30)"

    @staticmethod
    def admin_invalid_date_format() -> str:
        return "⚠️ Некорректный формат даты. Введите в формате ГГГГ-ММ-ДД (например: 2025-06-15)"

    @staticmethod
    def admin_stats(total: int, confirmed: int, cancelled: int, today: int, week: int) -> str:
        return (
            "📊 <b>Статистика</b>\n"
            "━━━━━━━━━━━━━━━━━\n"
            f"📋 Всего записей: <b>{total}</b>\n"
            f"✅ Активных: <b>{confirmed}</b>\n"
            f"❌ Отменённых: <b>{cancelled}</b>\n"
            f"📅 Сегодня: <b>{today}</b>\n"
            f"📆 За неделю: <b>{week}</b>"
        )

    @staticmethod
    def operation_cancelled() -> str:
        return "❌ Операция отменена."

    # ── Уведомления (мастер <-> клиент) ──────────────────────────────────

    @staticmethod
    def notify_admin_new_booking(
        client_name: str,
        phone: str,
        date: str,
        time: str,
        appt_id: int | None = None,
        username: str | None = None,
        user_id: int | None = None,
    ) -> str:
        formatted_date = _fmt_date(date)
        username_line = f"\n📲 @{_escape(username)}" if username else ""
        user_link = f" (tg://user?id={user_id})" if user_id else ""
        id_line = f"\n🆔 #{appt_id}" if appt_id else ""
        return (
            "🔔 <b>Новая запись!</b>\n"
            "─────────────────\n"
            f"👤 {_escape(client_name)}{username_line}{user_link}\n"
            f"📱 {_escape(phone)}\n"
            f"📅 {formatted_date}  🕐 {time}"
            f"{id_line}"
        )

    @staticmethod
    def notify_admin_cancellation(
        client_name: str,
        date: str,
        time: str,
        appt_id: int | None = None,
        username: str | None = None,
    ) -> str:
        formatted_date = _fmt_date(date)
        username_line = f" (@{_escape(username)})" if username else ""
        id_line = f" #{appt_id}" if appt_id else ""
        return (
            f"❌ <b>Отмена записи{id_line}</b>\n\n"
            f"👤 {_escape(client_name)}{username_line}\n"
            f"📅 {formatted_date}  🕐 {time}"
        )

    @staticmethod
    def notify_client_cancellation_by_admin(date: str, time: str, service_name: str = "мастеру") -> str:
        formatted_date = _fmt_date(date)
        return (
            f"😔 Ваша запись на {formatted_date} в {time} была отменена {service_name}.\n\n"
            "Если хотите перезаписаться — нажмите «Записаться» в меню 🌸"
        )

    @staticmethod
    def admin_daily_digest(date_str: str, appointments: list[Appointment]) -> str:
        """Утренний дайджест записей на день для администратора."""
        formatted_date = _fmt_date(date_str)
        if not appointments:
            return f"☀️ <b>Доброе утро!</b>\n\nНа {formatted_date} записей нет. Свободный день 🌸"
        lines = [f"☀️ <b>Доброе утро!</b>\n\nНа <b>{formatted_date}</b> — {len(appointments)} записей:\n"]
        for appt in appointments:
            lines.append(f"🕐 <b>{appt.time}</b> — {_escape(appt.client_name)}  📱 {_escape(appt.phone)}")
        return "\n".join(lines)

    @staticmethod
    def admin_2h_before_digest(appointments: list[Appointment]) -> str:
        """Уведомление за 2 часа до первой записи."""
        if not appointments:
            return ""
        first = appointments[0]
        lines = [f"⏰ <b>Напоминание!</b>\n\nЧерез ~2 часа первая запись — {first.time}\n"]
        for appt in appointments:
            lines.append(f"🕐 <b>{appt.time}</b> — {_escape(appt.client_name)}  📱 {_escape(appt.phone)}")
        return "\n".join(lines)

    # ── Поиск клиентов (admin) ────────────────────────────────────────────

    @staticmethod
    def admin_client_info(appt: Appointment) -> str:
        """Подробная карточка клиента для администратора."""
        formatted_date = _fmt_date(appt.date)
        username_line = f"\n📲 @{_escape(appt.username)}" if getattr(appt, 'username', None) else ""
        user_id_line = f"\n🔗 <a href=\"tg://user?id={appt.user_id}\">Написать клиенту</a>" if getattr(appt, 'user_id', None) else ""
        service_line = f"\n✨ {_escape(appt.service)}" if appt.service else ""
        comment_line = f"\n💬 {_escape(appt.comment)}" if appt.comment else ""
        status = "✅ активна" if not getattr(appt, 'is_cancelled', False) else "❌ отменена"
        return (
            f"👤 <b>{_escape(appt.client_name)}</b>{username_line}\n"
            f"📱 {_escape(appt.phone)}{user_id_line}\n"
            f"─────────────────\n"
            f"📅 {formatted_date}  🕐 {appt.time}"
            f"{service_line}"
            f"{comment_line}\n"
            f"Статус: {status}\n"
            f"🆔 #{appt.id}"
        )

    # ── Настройки ─────────────────────────────────────────────────────────

    @staticmethod
    def admin_settings_menu(settings_dict: dict) -> str:
        """Текущие настройки бота."""
        master_name = settings_dict.get("master_name", "—")
        welcome = settings_dict.get("welcome_text", "—")[:80] + "..."
        work_hours = settings_dict.get("work_hours", "—")
        slot_interval = settings_dict.get("slot_interval", "—")
        reminder_hours = settings_dict.get("reminder_hours", "—")
        services_count = settings_dict.get("services_count", 0)

        return (
            "⚙️ <b>Настройки бота</b>\n"
            "━━━━━━━━━━━━━━━━━\n"
            f"👤 Имя мастера: <b>{_escape(master_name)}</b>\n"
            f"💬 Приветствие: <i>{_escape(welcome)}</i>\n"
            f"🕐 Рабочие часы: <b>{_escape(str(work_hours))}</b>\n"
            f"⏱ Интервал записи: <b>{_escape(str(slot_interval))} мин</b>\n"
            f"🔔 Напоминание: <b>за {_escape(str(reminder_hours))} ч</b>\n"
            f"💅 Услуг: <b>{services_count}</b>\n"
            "━━━━━━━━━━━━━━━━━\n"
            "Что изменить?"
        )

    # ── Чёрный список ────────────────────────────────────────────────────

    # ── Дополнительные методы для совместимости ───────────────────────────

    @staticmethod
    def send_reminder(time: str, service_name: str = "маникюр") -> str:
        """Простое напоминание (для обратной совместимости)."""
        return f"🔔 Напоминание о записи на {time} ({service_name})"

    @staticmethod
    def slot_duration_with_end(time_str: str, duration_minutes: int) -> str:
        """Время слота с указанием окончания."""
        try:
            from datetime import datetime, timedelta
            start = datetime.strptime(time_str, "%H:%M")
            end = start + timedelta(minutes=duration_minutes)
            return f"{time_str}–{end.strftime('%H:%M')}"
        except Exception:
            return time_str

    @staticmethod
    def transfer_success(old_date: str, old_time: str, new_date: str, new_time: str) -> str:
        """Успешный перенос записи."""
        return (
            f"✅ Запись перенесена!\n\n"
            f"Было: {_fmt_date(old_date)} {old_time}\n"
            f"Стало: <b>{_fmt_date(new_date)} {new_time}</b> 🌸"
        )

    @staticmethod
    def insufficient_slots_warning(free_days_remaining: int, days_ahead: int) -> str:
        """Предупреждение о нехватке слотов для администратора."""
        return (
            f"⚠️ Осталось всего <b>{free_days_remaining}</b> дней с доступными слотами "
            f"(горизонт {days_ahead} дней).\nРекомендуется добавить рабочие дни."
        )

    @staticmethod
    def share_bot_link(bot_username: str) -> str:
        """Ссылка для поделиться ботом."""
        return f"💅 Записывайся на маникюр легко и быстро!\n\nhttps://t.me/{bot_username}"

    @staticmethod
    def admin_client_search_prompt() -> str:
        return "🔍 Введите имя или телефон клиента для поиска:"

    @staticmethod
    def booking_success_festive(date_str: str, time_str: str, service: str | None = None, hours_before: int = 24) -> str:
        """Праздничное подтверждение записи."""
        return MessageFormatter.booking_success(date_str, time_str, hours_before)

    @staticmethod
    def slot_button_label(time_str: str, duration_minutes: int, locked: bool = False) -> str:
        """Метка кнопки слота."""
        if locked:
            return f"🔒 {time_str}"
        return time_str

    @staticmethod
    def error_with_retry(reason: str | None = None) -> str:
        return MessageFormatter.error_general()

    @staticmethod
    def waitlist_notification(date: str, time: str) -> str:
        return MessageFormatter.waitlist_slot_available(date, time)

    @staticmethod
    def contact_info(phone: str = "", instagram: str = "", address: str = "", maps_link: str = "") -> str:
        return MessageFormatter.contacts_text(phone=phone or None, instagram=instagram or None,
                                               address=address or None, maps_link=maps_link or None)

    @staticmethod
    def price_list(services: dict) -> str:
        return MessageFormatter.prices_list(services)

    @staticmethod
    def schedule_view_for_client(dates: list[str], free_slots_per_date: dict) -> str:
        if not dates:
            return MessageFormatter.no_available_dates()
        lines = ["📅 <b>Ближайшие свободные дни:</b>\n"]
        for date_str in dates[:7]:
            times = free_slots_per_date.get(date_str, [])
            times_str = "  ·  ".join(times[:5]) if times else "нет слотов"
            lines.append(f"<b>{_fmt_date(date_str)}</b>\n{times_str}")
        return "\n\n".join(lines)

    @staticmethod
    def admin_stats_with_bars(done: int, cancelled: int, total: int) -> str:
        def bar(value: int, total_v: int, width: int = 10) -> str:
            if total_v == 0:
                return "░" * width
            filled = round(value / total_v * width)
            return "█" * filled + "░" * (width - filled)

        return (
            "📊 <b>Статистика</b>\n\n"
            f"✅ Выполнено: {done} {bar(done, total)}\n"
            f"❌ Отменено: {cancelled} {bar(cancelled, total)}\n"
            f"📋 Всего: {total}"
        )

    @staticmethod
    def dark_format_section(title: str, content: str) -> str:
        """Форматирует секцию с заголовком."""
        return f"<b>{title}</b>\n{content}"

    # ── Чёрный список ────────────────────────────────────────────────────

    @staticmethod
    def blacklist_info(user_ids: list[int]) -> str:
        if not user_ids:
            return "🚫 <b>Чёрный список</b>\n\nСписок пуст."
        lines = [f"🚫 <b>Чёрный список</b> ({len(user_ids)} польз.):\n"]
        for uid in user_ids:
            lines.append(f"• <code>{uid}</code>")
        return "\n".join(lines)

    @staticmethod
    def blacklist_user_added(user_id: int) -> str:
        return f"✅ Пользователь <code>{user_id}</code> добавлен в чёрный список."

    @staticmethod
    def blacklist_user_removed(user_id: int) -> str:
        return f"✅ Пользователь <code>{user_id}</code> удалён из чёрного списка."
