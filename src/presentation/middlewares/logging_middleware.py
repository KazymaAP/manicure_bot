"""
src/presentation/middlewares/logging_middleware.py — Middleware логирования.

✅ Из v2_tar: LoggingMiddleware
✅ Улучшения v4: замер времени выполнения, логирование типа апдейта
✅ FIXED: трекинг пользователей в таблице users для полноценной рассылки
"""
from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    """Middleware для логирования входящих апдейтов и времени выполнения.

    FIXED: также сохраняет/обновляет запись о пользователе в таблице users,
    чтобы рассылка могла охватить всех взаимодействовавших с ботом.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        start_time = time.monotonic()

        # event может быть различными объектами; используем TelegramObject для корректной типизации
        update: TelegramObject = data.get("event_update", event)
        update_type = "unknown"
        user_id = None
        from_user = None

        if hasattr(update, "message") and update.message:
            update_type = "message"
            from_user = update.message.from_user
            user_id = from_user.id if from_user else None
        elif hasattr(update, "callback_query") and update.callback_query:
            update_type = "callback_query"
            from_user = update.callback_query.from_user
            user_id = from_user.id if from_user else None

        logger.debug("Processing %s from user_id=%s", update_type, user_id)

        # FIXED: сохраняем/обновляем пользователя в таблице users
        if user_id and from_user:
            try:
                container = data.get("container")
                if container is not None:
                    db = getattr(container, "_db", None)
                    if db is not None:
                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        with db.transaction() as conn:
                            conn.execute(
                                """
                                INSERT INTO users (user_id, username, first_name, last_name, created_at, last_seen)
                                VALUES (?, ?, ?, ?, ?, ?)
                                ON CONFLICT(user_id) DO UPDATE SET
                                    username = excluded.username,
                                    first_name = excluded.first_name,
                                    last_name = excluded.last_name,
                                    last_seen = excluded.last_seen
                                """,
                                (
                                    user_id,
                                    getattr(from_user, "username", None),
                                    getattr(from_user, "first_name", None),
                                    getattr(from_user, "last_name", None),
                                    now_str,
                                    now_str,
                                )
                            )
            except Exception:
                # Не блокируем обработку при ошибке трекинга
                logger.debug("Failed to track user %s in users table", user_id, exc_info=True)

        result = await handler(event, data)

        elapsed = (time.monotonic() - start_time) * 1000
        logger.debug(
            "Handled %s from user_id=%s in %.1fms",
            update_type, user_id, elapsed,
        )
        return result
