"""
tests/unit/test_config/test_settings.py
Unit-тесты для Settings (pydantic).
"""
from __future__ import annotations

import os

import pytest
from pydantic import ValidationError

from src.config.settings import Settings


def make_settings(**kwargs) -> Settings:
    """Создаёт Settings с тестовыми значениями."""
    defaults = dict(
        BOT_TOKEN="1234567890:ABCDefGhIJKlmnoPQRStuvwXYZ",
        ADMIN_IDS="123456789",
    )
    defaults.update(kwargs)
    # Устанавливаем env vars для Pydantic Settings
    old_env = {}
    for k, v in defaults.items():
        old_env[k] = os.environ.get(k)
        os.environ[k] = str(v)
    try:
        return Settings()
    finally:
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class TestSettings:
    def test_admin_ids_parsed_correctly(self) -> None:
        """ADMIN_IDS='123,456' парсится в [123, 456]."""
        s = make_settings(ADMIN_IDS="123,456")
        assert s.admin_ids == [123, 456]

    def test_admin_ids_empty_returns_empty_list(self) -> None:
        """Пустой ADMIN_IDS возвращает []."""
        s = make_settings(ADMIN_IDS="")
        assert s.admin_ids == []

    def test_admin_ids_placeholder_returns_empty_list(self) -> None:
        """Placeholder ADMIN_IDS возвращает []."""
        s = make_settings(ADMIN_IDS="your_telegram_id_here")
        assert s.admin_ids == []

    def test_bot_token_empty_raises(self) -> None:
        """Пустой BOT_TOKEN вызывает ValidationError."""
        with pytest.raises((ValidationError, ValueError)):
            make_settings(BOT_TOKEN="")

    def test_default_time_slots_valid(self) -> None:
        """Слоты по умолчанию корректны."""
        s = make_settings()
        assert len(s.default_time_slots) > 0
        for slot in s.default_time_slots:
            assert len(slot) == 5
            assert slot[2] == ":"

    def test_schedule_days_ahead_range(self) -> None:
        """schedule_days_ahead в допустимом диапазоне [1, 365]."""
        s = make_settings()
        assert 1 <= s.schedule_days_ahead <= 365

    def test_reminder_hours_before_range(self) -> None:
        """reminder_hours_before в диапазоне [1, 72]."""
        s = make_settings()
        assert 1 <= s.reminder_hours_before <= 72

    def test_health_port_range(self) -> None:
        """health_port в диапазоне [1, 65535]."""
        s = make_settings()
        assert 1 <= s.health_port <= 65535
