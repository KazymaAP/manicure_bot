"""
src/presentation/keyboards/admin.py — Клавиатуры для административного интерфейса.

Обновлено: 6 разделов в главном меню, кнопки «Пришла» и «Отменить», 
управление расписанием слотами, настройки, чёрный список.
"""

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


class AdminKeyboard:
    """Фабрика клавиатур для администратора."""

    # ── Главное меню администратора — 6 разделов ─────────────────────────
    @staticmethod
    def main_menu() -> ReplyKeyboardMarkup:
        """
        Главное меню администратора с 6 разделами:
        1. Сегодня
        2. Все записи
        3. Расписание
        4. Клиенты
        5. Настройки
        6. Чёрный список
        """
        builder = ReplyKeyboardBuilder()
        builder.row(
            KeyboardButton(text="📅 Сегодня"),
            KeyboardButton(text="📋 Все записи"),
        )
        builder.row(
            KeyboardButton(text="🗓 Расписание"),
            KeyboardButton(text="👥 Клиенты"),
        )
        builder.row(
            KeyboardButton(text="⚙️ Настройки"),
            KeyboardButton(text="🚫 Чёрный список"),
        )
        builder.row(
            KeyboardButton(text="📊 Статистика"),
            KeyboardButton(text="📢 Рассылка"),
        )
        builder.row(
            KeyboardButton(text="⬇️ Экспорт CSV"),
        )
        builder.row(
            KeyboardButton(text="🏠 Главное меню"),
        )
        return builder.as_markup(resize_keyboard=True, one_time_keyboard=False)

    # ── Записи на сегодня — кнопки «Пришла» и «Отменить» ─────────────────
    @staticmethod
    def today_appointment_actions(appointment_id: int, client_name: str) -> InlineKeyboardMarkup:
        """Кнопки действий для записи на сегодня."""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✅ Пришла",
                callback_data=f"admin_arrived:{appointment_id}"
            ),
            InlineKeyboardButton(
                text="❌ Отменить",
                callback_data=f"admin_confirm_cancel:{appointment_id}"
            ),
        )
        return builder.as_markup()

    @staticmethod
    def today_appointments_list(appointments: list) -> InlineKeyboardMarkup:
        """Список записей на сегодня с кнопками действий."""
        builder = InlineKeyboardBuilder()
        for appt in appointments:
            appt_id = appt.id if appt.id is not None else 0
            builder.row(
                InlineKeyboardButton(
                    text=f"✅ {appt.time} {appt.client_name} — Пришла",
                    callback_data=f"admin_arrived:{appt_id}"
                ),
            )
            builder.row(
                InlineKeyboardButton(
                    text=f"❌ {appt.time} {appt.client_name} — Отменить",
                    callback_data=f"admin_confirm_cancel:{appt_id}"
                ),
            )
        return builder.as_markup()

    # ── Фильтр записей ────────────────────────────────────────────────────
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
        builder.row(
            InlineKeyboardButton(text="📊 По месяцам", callback_data="admin_monthly_stats"),
        )
        builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back_main"))
        return builder.as_markup()

    # ── Управление расписанием ────────────────────────────────────────────
    @staticmethod
    def schedule_menu() -> InlineKeyboardMarkup:
        """Меню управления расписанием."""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="📅 Просмотр дней", callback_data="admin_view_schedule"),
        )
        builder.row(
            InlineKeyboardButton(text="➕ Добавить слот", callback_data="admin_add_slot_manual"),
            InlineKeyboardButton(text="📅 Открыть неделю", callback_data="admin_open_week"),
        )
        builder.row(
            InlineKeyboardButton(text="🗓 Открыть день", callback_data="admin_open_day_cb"),
            InlineKeyboardButton(text="🔒 Закрыть день", callback_data="admin_close_day_cb"),
        )
        builder.row(
            InlineKeyboardButton(text="🚫 Массовая отмена", callback_data="admin_cancel_all_date_cb"),
        )
        builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back_main"))
        return builder.as_markup()

    @staticmethod
    def schedule_dates(dates: list[str]) -> InlineKeyboardMarkup:
        """Список дат расписания."""
        builder = InlineKeyboardBuilder()
        for date_str in dates[:20]:  # Ограничение для избежания превышения лимита Telegram
            builder.row(InlineKeyboardButton(
                text=date_str,
                callback_data=f"admin_date:{date_str}",
            ))
        builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back_schedule"))
        return builder.as_markup()

    @staticmethod
    def day_slots(date_str: str, slots: list[str]) -> InlineKeyboardMarkup:
        """
        Список слотов дня. Каждый слот можно открыть или закрыть для записи.
        Символ 🟢 = свободный, 📌 = занятый.
        """
        builder = InlineKeyboardBuilder()
        for time_str in slots:
            builder.row(
                InlineKeyboardButton(
                    text=f"🕐 {time_str}",
                    callback_data=f"admin_slot_info:{date_str}:{time_str}"
                ),
                InlineKeyboardButton(
                    text="❌ Удалить",
                    callback_data=f"admin_del_slot:{date_str}:{time_str}",
                ),
            )
        builder.row(
            InlineKeyboardButton(
                text="➕ Добавить слот",
                callback_data=f"admin_add_slot:{date_str}",
            )
        )
        builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back_schedule"))
        return builder.as_markup()

    @staticmethod
    def day_slots_with_status(date_str: str, slots_with_status: list[tuple[str, bool]]) -> InlineKeyboardMarkup:
        """
        Слоты с возможностью открытия/закрытия каждого.
        slots_with_status: [(time_str, is_booked), ...]
        """
        builder = InlineKeyboardBuilder()
        for time_str, is_booked in slots_with_status:
            status_icon = "📌" if is_booked else "🟢"
            action = "🔒 Закрыть" if not is_booked else "✅ Открыт"
            builder.row(
                InlineKeyboardButton(
                    text=f"{status_icon} {time_str}",
                    callback_data=f"admin_slot_info:{date_str}:{time_str}"
                ),
                InlineKeyboardButton(
                    text=action if not is_booked else "📌 Занят",
                    callback_data=f"admin_toggle_slot:{date_str}:{time_str}" if not is_booked else "admin_noop"
                ),
            )
        builder.row(
            InlineKeyboardButton(
                text="➕ Добавить слот",
                callback_data=f"admin_add_slot:{date_str}",
            )
        )
        builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back_schedule"))
        return builder.as_markup()

    # ── Подтверждение удаления слота ──────────────────────────────────────
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

    # ── Подтверждение отмены записи ───────────────────────────────────────
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

    # ── Клиенты ────────────────────────────────────────────────────────────
    @staticmethod
    def clients_menu() -> InlineKeyboardMarkup:
        """Меню управления клиентами."""
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="🔍 Найти по имени/телефону", callback_data="admin_find_client"))
        builder.row(InlineKeyboardButton(text="📋 История клиента", callback_data="admin_client_history"))
        builder.row(InlineKeyboardButton(text="✉️ Написать клиенту", callback_data="admin_message_client"))
        builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back_main"))
        return builder.as_markup()

    @staticmethod
    def client_actions(user_id: int, appt_id: int) -> InlineKeyboardMarkup:
        """Действия с клиентом."""
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(
            text="✉️ Написать клиенту",
            url=f"tg://user?id={user_id}"
        ))
        builder.row(
            InlineKeyboardButton(
                text="❌ Отменить запись",
                callback_data=f"admin_confirm_cancel:{appt_id}"
            )
        )
        builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back_clients"))
        return builder.as_markup()

    # ── Настройки ─────────────────────────────────────────────────────────
    @staticmethod
    def settings_menu() -> InlineKeyboardMarkup:
        """Меню настроек бота."""
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="✏️ Текст приветствия", callback_data="admin_edit_welcome"))
        builder.row(
            InlineKeyboardButton(text="💅 Услуги и цены", callback_data="admin_edit_services"),
        )
        builder.row(
            InlineKeyboardButton(text="🕐 Рабочие часы", callback_data="admin_edit_hours"),
            InlineKeyboardButton(text="⏱ Интервал записи", callback_data="admin_edit_interval"),
        )
        builder.row(InlineKeyboardButton(text="🔔 Время напоминания", callback_data="admin_edit_reminder"))
        builder.row(InlineKeyboardButton(text="📸 Фото приветствия", callback_data="admin_edit_photo"))
        builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back_main"))
        return builder.as_markup()

    @staticmethod
    def settings_services_menu() -> InlineKeyboardMarkup:
        """Меню управления услугами."""
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="➕ Добавить услугу", callback_data="admin_add_service"))
        builder.row(InlineKeyboardButton(text="✏️ Изменить услугу", callback_data="admin_edit_service"))
        builder.row(InlineKeyboardButton(text="❌ Удалить услугу", callback_data="admin_delete_service"))
        builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_settings"))
        return builder.as_markup()

    # ── Чёрный список ─────────────────────────────────────────────────────
    @staticmethod
    def blacklist_menu() -> InlineKeyboardMarkup:
        """Меню управления чёрным списком."""
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="➕ Заблокировать", callback_data="admin_block_user"),
            InlineKeyboardButton(text="➖ Разблокировать", callback_data="admin_unblock_user"),
        )
        builder.row(InlineKeyboardButton(text="📋 Список заблокированных", callback_data="admin_show_blacklist"))
        builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back_main"))
        return builder.as_markup()

    # ── Переключатель дня ─────────────────────────────────────────────────
    @staticmethod
    def toggle_day(date_str: str, is_working: bool) -> InlineKeyboardMarkup:
        label = "🔒 Закрыть день" if is_working else "🔓 Открыть день"
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text=label, callback_data=f"admin_toggle_day:{date_str}"))
        builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back_schedule"))
        return builder.as_markup()

    # ── Подтверждение массовой отмены ─────────────────────────────────────
    @staticmethod
    def cancel_all_confirm(date_str: str, count: int) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text=f"✅ Отменить {count} записей",
                callback_data=f"confirm_cancel_all:{date_str}",
            ),
            InlineKeyboardButton(text="❌ Отмена", callback_data="admin_back_main"),
        )
        return builder.as_markup()

    # ── Рассылка ──────────────────────────────────────────────────────────
    @staticmethod
    def broadcast_confirm(text_preview: str = "") -> InlineKeyboardMarkup:
        """Подтверждение рассылки с предпросмотром."""
        builder = InlineKeyboardBuilder()
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

    # ── Открыть неделю ────────────────────────────────────────────────────
    @staticmethod
    def open_week_confirm() -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="📅 Открыть 7 дней", callback_data="admin_open_week"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="admin_back_main"),
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

    # ── Отмена (FSM) ───────────────────────────────────────────────────────
    @staticmethod
    def cancel() -> ReplyKeyboardMarkup:
        """Кнопка отмены FSM-действия."""
        builder = ReplyKeyboardBuilder()
        builder.row(KeyboardButton(text="❌ Отмена"))
        return builder.as_markup(resize_keyboard=True)

    # ── Меню шаблонов расписания ──────────────────────────────────────────
    @staticmethod
    def templates_menu() -> InlineKeyboardMarkup:
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

    # ── Поиск клиента ─────────────────────────────────────────────────────
    @staticmethod
    def search_client_prompt() -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="🔎 Найти клиента", callback_data="admin_find_client"))
        builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back_main"))
        return builder.as_markup()
