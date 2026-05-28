"""
src/presentation/middlewares/logging_middleware.py — Middleware логирования.

✅ Из v2_tar: LoggingMiddleware
✅ Улучшения v4: замер времени выполнения, логирование типа апдейта
"""
from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    """Middleware для логирования входящих апдейтов и времени выполнения."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        start_time = time.monotonic()

        update: Update = data.get("event_update", event)
        update_type = "unknown"
        user_id = None

        if hasattr(update, "message") and update.message:
            update_type = "message"
            user_id = update.message.from_user.id if update.message.from_user else None
        elif hasattr(update, "callback_query") and update.callback_query:
            update_type = "callback_query"
            user_id = update.callback_query.from_user.id if update.callback_query.from_user else None

        logger.debug("Processing %s from user_id=%s", update_type, user_id)

        result = await handler(event, data)

        elapsed = (time.monotonic() - start_time) * 1000
        logger.debug(
            "Handled %s from user_id=%s in %.1fms",
            update_type, user_id, elapsed,
        )
        return result
