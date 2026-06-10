"""
tests/unit/test_security/test_xss_escaping.py — Тесты XSS-экранирования.

FIX #1: проверяет что пользовательские данные корректно экранируются
через html.escape() при вставке в HTML-сообщения.
"""
import html

import pytest

from src.presentation.formatters.message_formatter import MessageFormatter


class TestXSSEscaping:
    """Проверяет HTML-экранирование пользовательских данных."""

    XSS_PAYLOADS = [
        '<script>alert(1)</script>',
        '<b>Иван</b>',
        "O'Reilly & Associates",
    ]

    @pytest.mark.parametrize("payload", XSS_PAYLOADS)
    def test_admin_today_appointments_escapes_client_name(self, payload):
        """FIX #1: client_name экранируется в admin_today_appointments."""
        from src.domain.models.appointment import Appointment
        appt = Appointment(
            id=1, user_id=123, username=None,
            client_name=payload, phone="+79001234567",
            date="2025-06-15", time="10:00",
            service="маникюр", comment=None,
        )
        result = MessageFormatter.admin_today_appointments([appt])
        escaped = html.escape(payload)
        assert escaped in result, f"payload {payload!r} не экранирован"
        if any(c in payload for c in '<>"&'):
            assert payload not in result, f"сырой payload {payload!r} в выводе"

    def test_notify_admin_new_booking_escapes_data(self):
        """FIX #1: данные экранируются в notify_admin_new_booking."""
        payload = '<b>Иван</b>'
        result = MessageFormatter.notify_admin_new_booking(
            client_name=payload,
            phone='<i>+7900</i>',
            date='2025-06-15',
            time='10:00',
        )
        assert html.escape(payload) in result
        assert '<i>+7900</i>' not in result


class TestFromUserNoneGuard:
    """FIX #2/#3: проверяет наличие guard на from_user is None."""

    def test_admin_handler_has_from_user_guards(self):
        import inspect
        from src.presentation.handlers import admin_handler
        source = inspect.getsource(admin_handler)
        assert "from_user is None" in source

    def test_user_handler_has_from_user_guards(self):
        import inspect
        from src.presentation.handlers import user_handler
        source = inspect.getsource(user_handler)
        assert "from_user is None" in source

    def test_broadcast_tasks_is_module_level(self):
        """FIX #4: _broadcast_tasks определён на уровне модуля."""
        import inspect
        from src.presentation.handlers import admin_handler
        source = inspect.getsource(admin_handler)
        broadcast_pos = source.find("_broadcast_tasks")
        setup_pos = source.find("def setup_admin_router")
        assert broadcast_pos < setup_pos
