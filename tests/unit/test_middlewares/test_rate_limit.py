"""
tests/unit/test_middlewares/test_rate_limit.py
Unit-тесты для RateLimitMiddleware.
"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.presentation.middlewares.rate_limit_middleware import RateLimitMiddleware


def make_message_event(user_id: int = 1) -> MagicMock:
    """Создаёт мок-объект Message с указанным user_id."""
    from aiogram.types import Message
    event = MagicMock(spec=Message)
    event.from_user = MagicMock()
    event.from_user.id = user_id
    return event


class TestRateLimitMiddleware:
    def setup_method(self) -> None:
        self.middleware = RateLimitMiddleware(calls=3, per_seconds=5)

    @pytest.mark.asyncio
    async def test_allows_requests_within_limit(self) -> None:
        """Запросы в рамках лимита пропускаются."""
        handler = AsyncMock(return_value="ok")
        event = make_message_event(user_id=100)
        data: dict = {}
        for _ in range(3):
            result = await self.middleware(handler, event, data)
        assert handler.call_count == 3

    @pytest.mark.asyncio
    async def test_blocks_requests_over_limit(self) -> None:
        """Запросы сверх лимита блокируются (handler не вызывается)."""
        handler = AsyncMock(return_value="ok")
        event = make_message_event(user_id=200)
        data: dict = {}

        # 3 допустимых запроса
        for _ in range(3):
            await self.middleware(handler, event, data)

        # 4-й запрос должен быть заблокирован
        result = await self.middleware(handler, event, data)
        assert result is None
        assert handler.call_count == 3

    @pytest.mark.asyncio
    async def test_different_users_independent(self) -> None:
        """Пользователи независимы друг от друга."""
        handler = AsyncMock(return_value="ok")
        data: dict = {}

        user1_event = make_message_event(user_id=1)
        user2_event = make_message_event(user_id=2)

        # Исчерпываем лимит user1
        for _ in range(3):
            await self.middleware(handler, user1_event, data)
        assert handler.call_count == 3

        # user2 имеет независимый бакет — его запросы проходят
        await self.middleware(handler, user2_event, data)
        assert handler.call_count == 4

    @pytest.mark.asyncio
    async def test_cleanup_stale_buckets(self) -> None:
        """Устаревшие бакеты очищаются при периодической очистке."""
        handler = AsyncMock(return_value="ok")
        event = make_message_event(user_id=300)
        data: dict = {}

        await self.middleware(handler, event, data)
        assert 300 in self.middleware._buckets

        # Форсируем очистку: устанавливаем _last_cleanup в прошлое
        self.middleware._last_cleanup = time.time() - 1000
        # Делаем бакет "старым" — очищаем содержимое
        self.middleware._buckets[300].clear()

        # Следующий вызов (с другим user_id) должен вызвать очистку
        other_event = make_message_event(user_id=999)
        await self.middleware(handler, other_event, data)

        # Старый пустой бакет должен быть удалён
        assert 300 not in self.middleware._buckets
