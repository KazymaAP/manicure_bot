"""
src/presentation/keyboards/booking.py — Клавиатуры процесса записи.

✅ Из v2_tar: BookingKeyboard class
"""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.domain.models.time_slot import TimeSlot


class BookingKeyboard:
    """Клавиатуры для процесса записи клиента."""

    @staticmethod
    def time_slots(date_str: str, slots: list[TimeSlot]) -> InlineKeyboardMarkup:
        """Кнопки выбора времени.

        Args:
            date_str: Дата «YYYY-MM-DD».
            slots: Список свободных слотов.
        """
        builder = InlineKeyboardBuilder()
        for slot in slots:
            t_cb = slot.time.replace(":", "-")
            builder.button(
                text=f"🕐 {slot.time}",
                callback_data=f"slot:{date_str}:{t_cb}",
            )
        builder.adjust(3)
        builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="book_start"))
        return builder.as_markup()

    @staticmethod
    def confirm() -> InlineKeyboardMarkup:
        """Кнопки подтверждения / отмены записи."""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="booking_confirm"),
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
        """Кнопки отмены конкретной записи.

        Args:
            appointment_id: ID записи.
        """
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="❌ Отменить запись",
                callback_data=f"cancel_appt:{appointment_id}",
            )
        )
        builder.row(InlineKeyboardButton(text="⬅️ Главное меню", callback_data="main_menu"))
        return builder.as_markup()

    @staticmethod
    def cancel_appointment_list(appointments: list) -> InlineKeyboardMarkup:
        """Кнопки для отмены записей из списка.

        Args:
            appointments: Список записей.
        """
        builder = InlineKeyboardBuilder()
        for appt in appointments:
            builder.row(
                InlineKeyboardButton(
                    text=f"❌ {appt.date} {appt.time}",
                    callback_data=f"cancel_appt:{appt.id if appt.id is not None else 0}",
                )
            )
        builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"))
        return builder.as_markup()

    @staticmethod
    def after_cancel() -> InlineKeyboardMarkup:
        """Кнопка возврата в главное меню после отмены."""
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"))
        return builder.as_markup()
