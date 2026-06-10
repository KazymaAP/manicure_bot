"""
tests/unit/test_middlewares/test_rate_limit.py
Unit-тесты для RateLimitMiddleware.
"""
from __future__ import annotations

import time
from collections import deque
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


def make_callback_event(user_id: int = 1) -> MagicMock:
    """Создаёт мок-объект CallbackQuery с указанным user_id."""
    from aiogram.types import CallbackQuery
    event = MagicMock(spec=CallbackQuery)
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
            assert result == "ok"
        assert handler.call_count == 3

    @pytest.mark.asyncio
    async def test_blocks_requests_over_limit(self) -> None:
        """Запросы сверх лимита блокируются (handler не вызывается)."""
        handler = AsyncMock(return_value="ok")
        event = make_message_event(user_id=200)
        data: dict = {}

        for _ in range(3):
            await self.middleware(handler, event, data)

        # 4-й запрос должен быть заблокирован
        result = await self.middleware(handler, event, data)
        assert result is None
        assert handler.call_count == 3

    @pytest.mark.asyncio
    async def test_different_users_independent(self) -> None:
        """Пользователи независимы — лимит у каждого свой."""
        handler = AsyncMock(return_value="ok")
        data: dict = {}

        user1_event = make_message_event(user_id=1)
        user2_event = make_message_event(user_id=2)

        for _ in range(3):
            await self.middleware(handler, user1_event, data)
        assert handler.call_count == 3

        # user2 должен пройти
        await self.middleware(handler, user2_event, data)
        assert handler.call_count == 4

    @pytest.mark.asyncio
    async def test_callback_query_rate_limited(self) -> None:
        """CallbackQuery тоже rate-лимитируется."""
        handler = AsyncMock(return_value="ok")
        event = make_callback_event(user_id=500)
        data: dict = {}

        for _ in range(3):
            await self.middleware(handler, event, data)

        result = await self.middleware(handler, event, data)
        assert result is None

    @pytest.mark.asyncio
    async def test_cleanup_stale_buckets(self) -> None:
        """Устаревшие бакеты очищаются при периодической очистке."""
        handler = AsyncMock(return_value="ok")
        event = make_message_event(user_id=300)
        data: dict = {}

        await self.middleware(handler, event, data)
        assert 300 in self.middleware._buckets

        # Форсируем очистку
        self.middleware._last_cleanup = time.time() - 1000
        self.middleware._buckets[300].clear()  # пустой бакет

        other_event = make_message_event(user_id=999)
        await self.middleware(handler, other_event, data)

        # Старый пустой бакет удалён
        assert 300 not in self.middleware._buckets

    @pytest.mark.asyncio
    async def test_no_from_user_passes_through(self) -> None:
        """Если нет from_user — запрос пропускается без rate-ограничения."""
        from aiogram.types import Message
        handler = AsyncMock(return_value="ok")
        event = MagicMock(spec=Message)
        event.from_user = None
        data: dict = {}

        result = await self.middleware(handler, event, data)
        assert result == "ok"
        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_bucket_expiry(self) -> None:
        """После истечения per_seconds записи из bucket удаляются."""
        mw = RateLimitMiddleware(calls=2, per_seconds=1)
        handler = AsyncMock(return_value="ok")
        event = make_message_event(user_id=42)
        data: dict = {}

        # Заполняем бакет
        for _ in range(2):
            await mw(handler, event, data)
        assert handler.call_count == 2

        # Имитируем устаревание: очищаем деку вручную
        mw._buckets[42] = deque()

        # Теперь запрос должен пройти
        result = await mw(handler, event, data)
        assert result == "ok"
        assert handler.call_count == 3

    @pytest.mark.asyncio
    async def test_max_buckets_limit(self) -> None:
        """Словарь бакетов не превышает _MAX_BUCKETS."""
        from src.presentation.middlewares.rate_limit_middleware import _MAX_BUCKETS
        handler = AsyncMock(return_value="ok")
        data: dict = {}

        # Создаём _MAX_BUCKETS + 1 разных пользователей
        for user_id in range(_MAX_BUCKETS + 2):
            event = make_message_event(user_id=user_id)
            await self.middleware(handler, event, data)

        assert len(self.middleware._buckets) <= _MAX_BUCKETS + 1
