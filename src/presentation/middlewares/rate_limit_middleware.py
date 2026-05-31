from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    """Простой rate-limit middleware per-user.

    FIXED: предотвращает всплески от одного пользователя — ограничение по количеству
    операций в секундах. Для продакшена можно заменить на Redis-based throttling.
    FIXED: заменён threading.Lock на asyncio.Lock для безопасности в async контексте.
    """

    def __init__(self, calls: int = 5, per_seconds: int = 5) -> None:
        super().__init__()
        self.calls = calls
        self.per_seconds = per_seconds
        self._lock = asyncio.Lock()
        self._buckets: dict[int, list[float]] = defaultdict(list)

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
        async with self._lock:
            bucket = self._buckets[user_id]
            # Удаляем старые записи
            while bucket and bucket[0] <= now - self.per_seconds:
                bucket.pop(0)
            if len(bucket) >= self.calls:
                # превышение — отвечаем пользователю и логируем
                logger.warning("Rate limit exceeded for user %s: %s calls in %s seconds", user_id, self.calls, self.per_seconds)
                try:
                    bot = data.get("bot")
                    if bot:
                        await bot.send_message(user_id, "⏳ Подождите немного и попробуйте снова.")
                except Exception:
                    logger.exception("Failed to notify user about rate limit")
                return None
            bucket.append(now)
        return await handler(event, data)
        # FIXED: rate limit уменьшен до 5/5s и при превышении пользователь получает уведомление.
