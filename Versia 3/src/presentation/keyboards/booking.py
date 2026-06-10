"""
src/presentation/keyboards/booking.py — Клавиатуры процесса записи.

Обновлено: карточки услуг с ценой и длительностью, кнопки-слоты, тёплый UX.
"""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.domain.models.time_slot import TimeSlot

# Эмодзи для автоматического определения типа услуги
_SERVICE_EMOJIS = {
    "маникюр": "💅", "педикюр": "🦶", "покрытие": "✨",
    "гель": "💎", "наращивание": "🌟", "дизайн": "🎨",
    "удаление": "🧹", "чистка": "🫧", "парафин": "🕯",
    "оформление": "🌹", "укрепление": "🔮",
}


def _service_emoji(name: str) -> str:
    """Возвращает подходящий эмодзи для услуги."""
    name_lower = name.lower()
    for keyword, emoji in _SERVICE_EMOJIS.items():
        if keyword in name_lower:
            return emoji
    return "💅"


class BookingKeyboard:
    """Клавиатуры для процесса записи клиента."""

    @staticmethod
    def service_selection(services: dict | None = None) -> InlineKeyboardMarkup:
        """
        Карточки-кнопки услуг с названием, ценой и длительностью.
        Каждая услуга — отдельная кнопка с информацией.
        """
        builder = InlineKeyboardBuilder()
        if services:
            for name, info in services.items():
                emoji = _service_emoji(name)
                label_parts = [f"{emoji} {name}"]
                if isinstance(info, dict):
                    price = info.get("price")
                    duration = info.get("duration")
                    if price is not None:
                        label_parts.append(f"{price} ₽")
                    if duration is not None:
                        label_parts.append(f"{duration} мин")
                label = "  ·  ".join(label_parts) if len(label_parts) > 1 else label_parts[0]
                builder.row(InlineKeyboardButton(text=label, callback_data=f"service:{name}"))
        else:
            # Дефолтные услуги если настройки не заданы
            builder.row(InlineKeyboardButton(text="💅 Маникюр", callback_data="service:маникюр"))
            builder.row(InlineKeyboardButton(text="🦶 Педикюр", callback_data="service:педикюр"))
            builder.row(InlineKeyboardButton(text="✨ Покрытие гель-лаком", callback_data="service:покрытие"))
        return builder.as_markup()

    @staticmethod
    def time_slots(date_str: str, slots: list[TimeSlot]) -> InlineKeyboardMarkup:
        """
        Кнопки выбора времени — только свободные слоты.
        Аккуратная раскладка по 3 в ряд.
        """
        builder = InlineKeyboardBuilder()
        for slot in slots:
            t_cb = slot.time.replace(":", "-")
            builder.button(
                text=f"{slot.time}",
                callback_data=f"slot:{date_str}:{t_cb}",
            )
        builder.adjust(3)
        builder.row(InlineKeyboardButton(text="⬅️ Изменить дату", callback_data="book_start"))
        return builder.as_markup()

    @staticmethod
    def time_selection(times: list[str]) -> InlineKeyboardMarkup:
        """Выбор времени (используется при переносе записи)."""
        builder = InlineKeyboardBuilder()
        for t in times:
            builder.button(text=t, callback_data=f"time:{t}")
        builder.adjust(3)
        return builder.as_markup()

    @staticmethod
    def use_previous_data() -> InlineKeyboardMarkup:
        """Кнопка автозаполнения предыдущими данными."""
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(
            text="🔄 Использовать прошлые данные",
            callback_data="use_prev"
        ))
        return builder.as_markup()

    @staticmethod
    def confirm() -> InlineKeyboardMarkup:
        """Кнопки подтверждения / отмены записи."""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="✅ Всё верно!", callback_data="booking_confirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="booking_cancel"),
        )
        return builder.as_markup()

    @staticmethod
    def skip_comment() -> InlineKeyboardMarkup:
        """Кнопка пропуска комментария."""
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="➡️ Пропустить", callback_data="skip_comment"))
        return builder.as_markup()

    @staticmethod
    def cancel_appointment(appointment_id: int) -> InlineKeyboardMarkup:
        """Кнопка отмены конкретной записи."""
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(
            text="❌ Отменить запись",
            callback_data=f"cancel_appt:{appointment_id}",
        ))
        builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"))
        return builder.as_markup()

    @staticmethod
    def cancel_appointment_list(appointments: list) -> InlineKeyboardMarkup:
        """
        Список записей с кнопками отмены и переноса.
        Для каждой записи — строка с двумя кнопками.
        """
        builder = InlineKeyboardBuilder()
        for appt in appointments:
            appt_id = appt.id if appt.id is not None else 0
            builder.row(
                InlineKeyboardButton(
                    text=f"❌ Отменить {appt.date} {appt.time}",
                    callback_data=f"cancel_appt:{appt_id}",
                ),
                InlineKeyboardButton(
                    text="🔄 Перенести",
                    callback_data=f"transfer_appt:{appt_id}",
                ),
            )
        builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"))
        return builder.as_markup()

    @staticmethod
    def reminder_actions(appointment_id: int) -> InlineKeyboardMarkup:
        """Кнопки в напоминании: подтвердить приход, перенести или отменить.

        FIX #21: добавлена кнопка «🔄 Перенести» — позволяет клиенту
        перенести запись прямо из уведомления.
        """
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✅ Буду!",
                callback_data=f"reminder_yes:{appointment_id}"
            ),
            InlineKeyboardButton(
                text="🔄 Перенести",
                callback_data=f"transfer_appt:{appointment_id}"
            ),
        )
        builder.row(
            InlineKeyboardButton(
                text="❌ Отменить запись",
                callback_data=f"reminder_no:{appointment_id}"
            ),
        )
        return builder.as_markup()

    @staticmethod
    def book_again() -> InlineKeyboardMarkup:
        """Кнопка записаться снова (после визита)."""
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(
            text="💅 Записаться снова",
            callback_data="book_again_start"
        ))
        return builder.as_markup()

    @staticmethod
    def after_cancel() -> InlineKeyboardMarkup:
        """Кнопка возврата в главное меню после отмены."""
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"))
        return builder.as_markup()

    @staticmethod
    def waitlist_notify(date_str: str, time_str: str) -> InlineKeyboardMarkup:
        """Кнопки при уведомлении из листа ожидания."""
        t_cb = time_str.replace(":", "-")
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✅ Записаться!",
                callback_data=f"waitlist_book:{date_str}:{t_cb}"
            ),
            InlineKeyboardButton(
                text="❌ Не нужно",
                callback_data="waitlist_decline"
            ),
        )
        return builder.as_markup()
