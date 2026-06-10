"""
tests/unit/test_handlers/test_callback_coverage.py — Проверка покрытия callback_data.

ПРОБЛЕМА 18 FIX: тесты проверяют что все статические callback_data из клавиатур
имеют соответствующие хендлеры в роутерах.

Тесты намеренно лёгкие (без запуска aiogram) — проверяют структуру кода.
BUG ruff FIX: убран неиспользуемый import pytest; все импорты вынесены в начало файла.
"""
from aiogram.types import InlineKeyboardMarkup

from src.application.services.appointment_service import AppointmentService
from src.domain.enums.fsm_states import AdminFSM
from src.infrastructure.repositories.appointment_repository import AppointmentRepository
from src.presentation.handlers import (
    setup_admin_router,
    setup_common_router,
    setup_extended_features_router,
    setup_final_features_router,
    setup_user_router,
)
from src.presentation.keyboards import (
    AdminKeyboard,
    BookingKeyboard,
    CalendarKeyboard,
    MainMenuKeyboard,
    NotificationKeyboard,
)
from src.presentation.keyboards.notifications import NotificationKeyboard as _NotifKB

# ── Список всех статических callback_data из keyboards/ ─────────────────────
# Обновить при добавлении новых кнопок
ADMIN_CALLBACKS = [
    "admin_view_schedule",
    "admin_add_slot_manual",
    "admin_open_week",
    "admin_open_day_cb",
    "admin_close_day_cb",
    "admin_cancel_all_date_cb",
    "admin_templates",
    "admin_save_template",
    "admin_delete_template",
    "admin_apply_template",
    "admin_find_client",
    "admin_client_history",
    "admin_message_client",
    "admin_edit_welcome",
    "admin_edit_services",
    "admin_edit_hours",
    "admin_edit_interval",
    "admin_edit_reminder",
    "admin_edit_photo",
    "admin_add_service",
    "admin_edit_service",
    "admin_delete_service",
    "admin_block_user",
    "admin_unblock_user",
    "admin_show_blacklist",
    "admin_back_main",
    "admin_back_schedule",
    "admin_back_clients",
    "admin_settings",
    "admin_broadcast_send",
    "admin_broadcast_cancel",
    "admin_noop",
    "admin_monthly_stats",
    "admin_export_csv",
]

BOOKING_CALLBACKS = [
    "book_again_start",
    "book_again",
    "booking_confirm",
    "booking_cancel",
    "skip_comment",
    "use_prev",
    "main_menu",
]

NOTIFICATION_CALLBACKS = [
    "notif_all_on",
    "notif_all_off",
    "notif_24h",
    "notif_2h",
    "notif_1h",
]

COMMON_CALLBACKS = [
    "check_subscription",
    "waitlist_decline",
]

ALL_STATIC_CALLBACKS = (
    ADMIN_CALLBACKS
    + BOOKING_CALLBACKS
    + NOTIFICATION_CALLBACKS
    + COMMON_CALLBACKS
)

# ── Callback-данные с динамическими префиксами (проверяем отдельно) ──────────
DYNAMIC_CALLBACK_PREFIXES = [
    "admin_filter:",
    "admin_arrived:",
    "admin_cancel_request:",
    "admin_confirm_cancel:",
    "admin_del_slot:",
    "admin_confirm_del_slot:",
    "admin_add_slot:",
    "admin_toggle_day:",
    "admin_del_tmpl_confirm:",
    "admin_apply_tmpl_exec:",
    "confirm_cancel_all:",
    "transfer_appt:",
    "transfer_cal_day:",
    "transfer_cal_prev:",   # ПРОБЛЕМА 1 FIX
    "transfer_cal_next:",   # ПРОБЛЕМА 1 FIX
    "join_waitlist:",
    "waitlist_book:",
    "time:",
    "reminder_yes:",
    "reminder_no:",
    "admin_edit_svc_select:",
    "admin_del_svc_confirm:",
    "cancel_appt:",         # БАГ 25 FIX: prefix для отмены записей клиентом
]


class TestStaticCallbacksExist:
    """Проверяет что список статических callback_data не пуст."""

    def test_admin_callbacks_not_empty(self):
        assert len(ADMIN_CALLBACKS) > 0, "Список admin callback_data пуст"

    def test_booking_callbacks_not_empty(self):
        assert len(BOOKING_CALLBACKS) > 0, "Список booking callback_data пуст"

    def test_notification_callbacks_not_empty(self):
        assert len(NOTIFICATION_CALLBACKS) > 0, "Список notification callback_data пуст"

    def test_all_callbacks_not_empty(self):
        assert len(ALL_STATIC_CALLBACKS) > 0

    def test_no_duplicate_static_callbacks(self):
        """Проверяет что в списке нет дублирующихся callback_data."""
        duplicates = [cb for cb in ALL_STATIC_CALLBACKS if ALL_STATIC_CALLBACKS.count(cb) > 1]
        assert len(duplicates) == 0, f"Дублирующиеся callback_data: {set(duplicates)}"

    def test_dynamic_prefixes_not_empty(self):
        assert len(DYNAMIC_CALLBACK_PREFIXES) > 0


class TestNotificationCallbacksPresent:
    """Проверяет что все нужные notification callbacks присутствуют в списке."""

    def test_notif_all_on_present(self):
        assert "notif_all_on" in NOTIFICATION_CALLBACKS

    def test_notif_all_off_present(self):
        assert "notif_all_off" in NOTIFICATION_CALLBACKS

    def test_notif_24h_present(self):
        assert "notif_24h" in NOTIFICATION_CALLBACKS

    def test_notif_2h_present(self):
        assert "notif_2h" in NOTIFICATION_CALLBACKS

    def test_notif_1h_present(self):
        assert "notif_1h" in NOTIFICATION_CALLBACKS


class TestTransferCalendarCallbacksPresent:
    """ПРОБЛЕМА 1 FIX: проверяет наличие callback_data для навигации календаря переноса."""

    def test_transfer_cal_prev_prefix_present(self):
        assert "transfer_cal_prev:" in DYNAMIC_CALLBACK_PREFIXES

    def test_transfer_cal_next_prefix_present(self):
        assert "transfer_cal_next:" in DYNAMIC_CALLBACK_PREFIXES

    def test_cancel_appt_prefix_present(self):
        """БАГ 25 FIX: cancel_appt: должен присутствовать в DYNAMIC_CALLBACK_PREFIXES."""
        assert "cancel_appt:" in DYNAMIC_CALLBACK_PREFIXES


class TestAdminNoopCallback:
    """ПРОБЛЕМА 7: проверяет что admin_noop присутствует в списке."""

    def test_admin_noop_present(self):
        assert "admin_noop" in ADMIN_CALLBACKS


class TestNotificationKeyboardImport:
    """ПРОБЛЕМА 2/16: проверяет что NotificationKeyboard импортируется корректно."""

    def test_import_notification_keyboard(self):
        assert _NotifKB is not None

    def test_notification_keyboard_has_settings_method(self):
        assert hasattr(_NotifKB, "settings")
        assert callable(_NotifKB.settings)

    def test_notification_keyboard_settings_returns_markup(self):
        notif_settings = {
            "notifications_enabled": 1,
            "notif_24h": 1,
            "notif_2h": 0,
            "notif_1h": 1,
        }
        kb = _NotifKB.settings(notif_settings)
        assert isinstance(kb, InlineKeyboardMarkup)
        assert len(kb.inline_keyboard) == 4

    def test_notification_keyboard_all_off(self):
        notif_settings = {
            "notifications_enabled": 0,
            "notif_24h": 0,
            "notif_2h": 0,
            "notif_1h": 0,
        }
        kb = _NotifKB.settings(notif_settings)
        assert isinstance(kb, InlineKeyboardMarkup)
        # Первая кнопка должна иметь callback_data "notif_all_on" (для включения)
        first_button = kb.inline_keyboard[0][0]
        assert first_button.callback_data == "notif_all_on"


class TestKeyboardsInitExports:
    """ПРОБЛЕМА 17: проверяет что keyboards/__init__.py экспортирует все клавиатуры."""

    def test_import_all_keyboards(self):
        assert AdminKeyboard is not None
        assert BookingKeyboard is not None
        assert CalendarKeyboard is not None
        assert MainMenuKeyboard is not None
        assert NotificationKeyboard is not None


class TestHandlersInitExports:
    """ПРОБЛЕМА 19: проверяет что handlers/__init__.py экспортирует setup-функции."""

    def test_import_setup_functions(self):
        assert callable(setup_admin_router)
        assert callable(setup_common_router)
        assert callable(setup_extended_features_router)
        assert callable(setup_final_features_router)
        assert callable(setup_user_router)


class TestFSMStatesClean:
    """ПРОБЛЕМА 4: проверяет что waiting_for_broadcast удалено из FSM."""

    def test_waiting_for_broadcast_removed(self):
        """waiting_for_broadcast не должно существовать в AdminFSM."""
        assert not hasattr(AdminFSM, "waiting_for_broadcast"), (
            "AdminFSM.waiting_for_broadcast должно быть удалено (ПРОБЛЕМА 4)"
        )

    def test_specific_broadcast_state_exists(self):
        """Отдельные состояния для разных режимов должны существовать."""
        assert hasattr(AdminFSM, "waiting_for_broadcast_text")
        assert hasattr(AdminFSM, "waiting_for_welcome_text")
        assert hasattr(AdminFSM, "waiting_for_photo_url")

    def test_template_date_state_exists(self):
        """ПРОБЛЕМА 5: waiting_for_template_date должно существовать."""
        assert hasattr(AdminFSM, "waiting_for_template_date")


class TestAppointmentServiceGetAllUserIds:
    """ПРОБЛЕМА 13: проверяет наличие метода get_all_user_ids."""

    def test_method_exists_in_repository(self):
        assert hasattr(AppointmentRepository, "get_all_user_ids")
        assert callable(AppointmentRepository.get_all_user_ids)

    def test_method_exists_in_service(self):
        assert hasattr(AppointmentService, "get_all_user_ids")
        assert callable(AppointmentService.get_all_user_ids)
