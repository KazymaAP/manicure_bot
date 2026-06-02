"""
tests/unit/test_config/test_settings.py
Unit-тесты для Settings (pydantic).
"""
from __future__ import annotations

import os
from contextlib import contextmanager

import pytest
from pydantic import ValidationError

from src.config.settings import Settings


@contextmanager
def env_override(**kwargs):
    """Контекстный менеджер для временного переопределения env vars."""
    old = {}
    for k, v in kwargs.items():
        old[k] = os.environ.get(k)
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = str(v)
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def make_settings(**kwargs) -> Settings:
    """Создаёт Settings с тестовыми значениями."""
    defaults = {
        "BOT_TOKEN": "1234567890:ABCDefGhIJKlmnoPQRStuvwXYZ",
        "ADMIN_IDS": "123456789",
    }
    defaults.update(kwargs)
    with env_override(**defaults):
        return Settings()


class TestAdminIds:
    def test_single_id(self) -> None:
        s = make_settings(ADMIN_IDS="123456789")
        assert s.admin_ids == [123456789]

    def test_multiple_ids(self) -> None:
        s = make_settings(ADMIN_IDS="123,456,789")
        assert s.admin_ids == [123, 456, 789]

    def test_ids_with_spaces(self) -> None:
        s = make_settings(ADMIN_IDS=" 123 , 456 ")
        assert s.admin_ids == [123, 456]

    def test_empty_returns_empty_list(self) -> None:
        s = make_settings(ADMIN_IDS="")
        assert s.admin_ids == []

    def test_placeholder_returns_empty_list(self) -> None:
        for placeholder in ("your_telegram_id_here", "your_telegram_id"):
            s = make_settings(ADMIN_IDS=placeholder)
            assert s.admin_ids == []

    def test_invalid_non_numeric_filtered(self) -> None:
        """Нечисловые значения фильтруются из списка."""
        s = make_settings(ADMIN_IDS="123,abc,456")
        assert 123 in s.admin_ids
        assert 456 in s.admin_ids


class TestBotToken:
    def test_empty_token_raises(self) -> None:
        with pytest.raises((ValidationError, ValueError)):
            make_settings(BOT_TOKEN="")

    def test_valid_token(self) -> None:
        s = make_settings(BOT_TOKEN="1234567890:ABCdef")
        assert s.bot_token.get_secret_value() == "1234567890:ABCdef"

    def test_token_is_secret(self) -> None:
        """Токен должен быть SecretStr (не виден в repr/str)."""
        s = make_settings()
        repr_str = repr(s.bot_token)
        assert "ABCDef" not in repr_str
        assert "**" in repr_str or "SecretStr" in repr_str


class TestTimeSlots:
    def test_default_time_slots_valid(self) -> None:
        s = make_settings()
        assert len(s.default_time_slots) > 0
        for slot in s.default_time_slots:
            assert len(slot) == 5
            assert slot[2] == ":"
            h, m = map(int, slot.split(":"))
            assert 0 <= h < 24
            assert 0 <= m < 60

    def test_invalid_time_slot_format_raises(self) -> None:
        with pytest.raises((ValidationError, ValueError)):
            make_settings(DEFAULT_TIME_SLOTS='["9:00"]')

    def test_custom_time_slots(self) -> None:
        s = make_settings(DEFAULT_TIME_SLOTS='["09:00","14:30","18:00"]')
        assert "09:00" in s.default_time_slots
        assert "14:30" in s.default_time_slots


class TestRangeValidation:
    def test_schedule_days_ahead_default(self) -> None:
        s = make_settings()
        assert 1 <= s.schedule_days_ahead <= 365

    def test_reminder_hours_before_default(self) -> None:
        s = make_settings()
        assert 1 <= s.reminder_hours_before <= 72

    def test_health_port_default(self) -> None:
        s = make_settings()
        assert 1 <= s.health_port <= 65535

    def test_max_appointments_per_user_default(self) -> None:
        s = make_settings()
        assert 1 <= s.max_appointments_per_user <= 10

    def test_custom_reminder_hours(self) -> None:
        s = make_settings(REMINDER_HOURS_BEFORE="48")
        assert s.reminder_hours_before == 48

    def test_custom_schedule_days(self) -> None:
        s = make_settings(SCHEDULE_DAYS_AHEAD="60")
        assert s.schedule_days_ahead == 60


class TestOptionalFields:
    def test_portfolio_url_default_none(self) -> None:
        s = make_settings()
        assert s.portfolio_url is None

    def test_redis_url_default_none(self) -> None:
        s = make_settings()
        assert s.redis_url is None

    def test_required_channel_default_none(self) -> None:
        s = make_settings()
        assert s.required_channel is None

    def test_metrics_token_default_none(self) -> None:
        s = make_settings()
        assert s.metrics_token is None

    def test_welcome_photo_url_default_none(self) -> None:
        s = make_settings()
        assert s.welcome_photo_url is None

    def test_timezone_default_utc(self) -> None:
        s = make_settings()
        assert s.timezone == "UTC"

    def test_custom_timezone(self) -> None:
        s = make_settings(TIMEZONE="Europe/Moscow")
        assert s.timezone == "Europe/Moscow"


class TestServicesValidation:
    def test_valid_services(self) -> None:
        services_json = '{"маникюр": {"price": 1200, "duration": 60}}'
        s = make_settings(SERVICES=services_json)
        assert "маникюр" in s.services
        assert s.services["маникюр"]["price"] == 1200

    def test_empty_services(self) -> None:
        s = make_settings(SERVICES="{}")
        assert s.services == {}
