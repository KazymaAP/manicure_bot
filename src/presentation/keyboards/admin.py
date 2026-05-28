# src/presentation/keyboards/admin.py
"""Клавиатуры для административного интерфейса."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


class AdminKeyboard:
    """Фабрика клавиатур для администратора."""

    # ── Главное меню администратора ──────────────────────────────────────
    @staticmethod
    def main_menu() -> ReplyKeyboardMarkup:
        builder = ReplyKeyboardBuilder()
        builder.row(
            KeyboardButton(text="📋 Все записи"),
            KeyboardButton(text="📅 Расписание"),
        )
        builder.row(
            KeyboardButton(text="➕ Добавить слот"),
            KeyboardButton(text="🗓 Открыть день"),
        )
        builder.row(
            KeyboardButton(text="🔒 Закрыть день"),
            KeyboardButton(text="❌ Отменить запись"),
        )
        builder.row(
            KeyboardButton(text="📊 Статистика"),
            KeyboardButton(text="🏠 Главное меню"),
        )
        return builder.as_markup(resize_keyboard=True, one_time_keyboard=False)

    @staticmethod
    def cancel() -> ReplyKeyboardMarkup:
        """Кнопка отмены."""
        builder = ReplyKeyboardBuilder()
        builder.row(KeyboardButton(text="❌ Отмена"))
        return builder.as_markup(resize_keyboard=True)

    # ── Подтверждение отмены записи ──────────────────────────────────────
    @staticmethod
    def confirm_cancel(appointment_id: int) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✅ Да, отменить",
                callback_data=f"admin_confirm_cancel:{appointment_id}",
            ),
            InlineKeyboardButton(
                text="❌ Нет, оставить",
                callback_data=f"admin_cancel_abort:{appointment_id}",
            ),
        )
        return builder.as_markup()

    # ── Список дат расписания ────────────────────────────────────────────
    @staticmethod
    def schedule_dates(dates: list[str]) -> InlineKeyboardMarkup:
        """dates — список строк «YYYY-MM-DD»."""
        builder = InlineKeyboardBuilder()
        for date_str in dates:
            builder.row(
                InlineKeyboardButton(
                    text=date_str,
                    callback_data=f"admin_date:{date_str}",
                )
            )
        builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back_main"))
        return builder.as_markup()

    # ── Список слотов выбранного дня (для удаления) ──────────────────────
    @staticmethod
    def day_slots(date_str: str, slots: list[str]) -> InlineKeyboardMarkup:
        """slots — список строк «HH:MM»."""
        builder = InlineKeyboardBuilder()
        for time_str in slots:
            builder.row(
                InlineKeyboardButton(
                    text=f"🕐 {time_str}  ❌",
                    callback_data=f"admin_del_slot:{date_str}:{time_str}",
                )
            )
        builder.row(
            InlineKeyboardButton(
                text="➕ Добавить слот",
                callback_data=f"admin_add_slot:{date_str}",
            )
        )
        builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back_schedule"))
        return builder.as_markup()

    # ── Подтверждение удаления слота ─────────────────────────────────────
    @staticmethod
    def confirm_delete_slot(date_str: str, time_str: str) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✅ Удалить",
                callback_data=f"admin_confirm_del_slot:{date_str}:{time_str}",
            ),
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data=f"admin_date:{date_str}",
            ),
        )
        return builder.as_markup()

    # ── Переключатель статуса рабочего дня ───────────────────────────────
    @staticmethod
    def toggle_day(date_str: str, is_working: bool) -> InlineKeyboardMarkup:
        label = "🔒 Закрыть день" if is_working else "🔓 Открыть день"
        callback = f"admin_toggle_day:{date_str}"
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text=label, callback_data=callback))
        builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back_schedule"))
        return builder.as_markup()

    # ── Кнопка «Отмена» для FSM шагов ───────────────────────────────────
    # ── Фильтры для просмотра записей ────────────────────────────────────
    @staticmethod
    def appointments_filter() -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="📅 На сегодня", callback_data="admin_filter:today"),
            InlineKeyboardButton(text="📆 На неделю", callback_data="admin_filter:week"),
        )
        builder.row(
            InlineKeyboardButton(text="📋 Все активные", callback_data="admin_filter:active"),
            InlineKeyboardButton(text="🗂 Все", callback_data="admin_filter:all"),
        )
        builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back_main"))
        return builder.as_markup()
