from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

logger = logging.getLogger(__name__)

# Максимальный размер словаря бакетов (защита от утечки памяти)
_MAX_BUCKETS = 10_000


class RateLimitMiddleware(BaseMiddleware):
    """Простой rate-limit middleware per-user.

    FIXED: предотвращает всплески от одного пользователя.
    FIXED: используем deque вместо list для O(1) операций pop из начала.
    FIXED: ограничен размер словаря бакетов (_MAX_BUCKETS) для защиты памяти.
    FIXED: убран asyncio.Lock на весь хэндлер — не нужен при deque + per-user scope.
    """

    def __init__(self, calls: int = 5, per_seconds: int = 5) -> None:
        super().__init__()
        self.calls = calls
        self.per_seconds = per_seconds
        # FIXED: deque вместо list — O(1) удаление из начала
        self._buckets: dict[int, deque[float]] = defaultdict(deque)

    async def __call__(self, handler, event: TelegramObject, data: dict[str, Any]):
        user_id = None
        try:
            # пытаемся извлечь user_id из известных мест
            update = data.get("event_update", event)
            if hasattr(update, "message") and getattr(update, "message") is not None:
                user_id = getattr(update.message.from_user, "id", None)
            elif hasattr(update, "callback_query") and getattr(update, "callback_query") is not None:
                user_id = getattr(update.callback_query.from_user, "id", None)
        except Exception:
            user_id = None

        if user_id is None:
            return await handler(event, data)

        now = time.time()
        bucket = self._buckets[user_id]

        # Удаляем старые записи (deque — O(1))
        while bucket and bucket[0] <= now - self.per_seconds:
            bucket.popleft()

        if len(bucket) >= self.calls:
            # превышение — отвечаем пользователю и логируем
            logger.warning(
                "Rate limit exceeded for user %s: %s calls in %s seconds",
                user_id, self.calls, self.per_seconds,
            )
            try:
                bot = data.get("bot")
                if bot:
                    await bot.send_message(user_id, "⏳ Подождите немного и попробуйте снова.")
            except Exception:
                logger.exception("Failed to notify user about rate limit")
            return None

        bucket.append(now)

        # FIXED: ограничиваем размер словаря бакетов для защиты от утечки памяти
        if len(self._buckets) > _MAX_BUCKETS:
            # Удаляем самый старый бакет
            oldest_uid = next(iter(self._buckets))
            del self._buckets[oldest_uid]

        return await handler(event, data)
