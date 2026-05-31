# src/presentation/keyboards/admin.py
"""Клавиатуры для административного интерфейса."""

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
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
            KeyboardButton(text="📢 Рассылка"),
        )
        builder.row(
            KeyboardButton(text="⬇️ Экспорт CSV"),
            KeyboardButton(text="📅 Открыть неделю"),
        )
        builder.row(
            KeyboardButton(text="🔍 Найти клиента"),
            KeyboardButton(text="🛑 Черный список"),
        )
        builder.row(
            KeyboardButton(text="🏠 Главное меню"),
        )
        return builder.as_markup(resize_keyboard=True, one_time_keyboard=False)

    @staticmethod
    def broadcast_confirm(text_preview: str = "") -> InlineKeyboardMarkup:
        """Клавиатура подтверждения рассылки.

        FIXED BUG-H6: параметр text_preview ранее принимался, но нигде не использовался
        (мёртвый параметр). Теперь он используется для предпросмотра в тексте кнопки —
        показываем первые 30 символов в заголовке кнопки для наглядности.
        Параметр по умолчанию пустой для обратной совместимости.
        """
        builder = InlineKeyboardBuilder()
        # Показываем предпросмотр текста в кнопке (до 30 символов)
        preview_label = ""
        if text_preview:
            clean = text_preview.strip().replace("\n", " ")
            preview_label = f': "{clean[:30]}…"' if len(clean) > 30 else f': "{clean}"'
        builder.row(
            InlineKeyboardButton(
                text=f"✅ Отправить всем{preview_label}",
                callback_data="admin_broadcast_send",
            ),
            InlineKeyboardButton(text="❌ Отмена", callback_data="admin_broadcast_cancel"),
        )
        return builder.as_markup()

    @staticmethod
    def export_csv_confirm() -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="✅ Экспорт за период", callback_data="admin_export_csv"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="admin_back_main"),
        )
        return builder.as_markup()

    @staticmethod
    def open_week_confirm() -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="📅 Открыть 7 дней", callback_data="admin_open_week"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="admin_back_main"),
        )
        return builder.as_markup()

    @staticmethod
    def blacklist_menu() -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="➕ Заблокировать", callback_data="admin_block_user"),
            InlineKeyboardButton(text="➖ Разблокировать", callback_data="admin_unblock_user"),
        )
        builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back_main"))
        return builder.as_markup()

    @staticmethod
    def search_client_prompt() -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="🔎 Найти клиента", callback_data="admin_find_client"))
        builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back_main"))
        return builder.as_markup()

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

    # ── Меню управления шаблонами расписания ─────────────────────────────
    @staticmethod
    def templates_menu() -> InlineKeyboardMarkup:
        """FIXED: меню для сохранения/применения шаблонов расписания."""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="➕ Сохранить шаблон", callback_data="admin_save_template"),
            InlineKeyboardButton(text="➖ Удалить шаблон", callback_data="admin_delete_template"),
        )
        builder.row(
            InlineKeyboardButton(text="📋 Применить шаблон", callback_data="admin_apply_template"),
            InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back_main"),
        )
        return builder.as_markup()

    # ── Меню отмены всех записей на дату ─────────────────────────────────
    @staticmethod
    def cancel_all_confirm(date_str: str, count: int) -> InlineKeyboardMarkup:
        """FIXED: подтверждение массовой отмены."""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text=f"✅ Отменить {count} записей",
                callback_data=f"confirm_cancel_all:{date_str}",
            ),
            InlineKeyboardButton(text="❌ Отмена", callback_data="admin_back_main"),
        )
        return builder.as_markup()
