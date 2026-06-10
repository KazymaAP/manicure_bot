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
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    """Middleware для логирования входящих апдейтов и времени выполнения.

    FIXED H-02: в aiogram 3.x event в middleware уже является конкретным типом
    (Message, CallbackQuery и т.д.), а не Update. Используем isinstance() для
    корректного извлечения user_id и from_user вместо проверки update.message / update.callback_query.

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

        # FIXED H-02: используем isinstance() вместо hasattr(update, "message") —
        # в aiogram 3.x event уже является Message/CallbackQuery, а не Update.
        # Проверка hasattr(update, "message") всегда False для Message (у него нет поля .message).
        update_type = "unknown"
        user_id = None
        from_user = None

        if isinstance(event, Message):
            update_type = "message"
            from_user = event.from_user
            user_id = from_user.id if from_user else None
        elif isinstance(event, CallbackQuery):
            update_type = "callback_query"
            from_user = event.from_user
            user_id = from_user.id if from_user else None
        else:
            # Для прочих типов (InlineQuery и т.д.) пробуем через from_user напрямую
            from_user = getattr(event, "from_user", None)
            if from_user:
                user_id = getattr(from_user, "id", None)
                update_type = type(event).__name__.lower()

        logger.debug("Processing %s from user_id=%s", update_type, user_id)

        # FIXED H-08: трекинг пользователя в БД выполняется через asyncio.to_thread
        # чтобы не блокировать event loop на время синхронного SQLite-вызова.
        if user_id and from_user:
            try:
                container = data.get("container")
                if container is not None:
                    # ПРОБЛЕМА 12 FIX: используем container.db напрямую вместо getattr-обхода
                    db = container.db
                    if db is not None:
                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        _uid = user_id
                        _uname = getattr(from_user, "username", None)
                        _fname = getattr(from_user, "first_name", None)
                        _lname = getattr(from_user, "last_name", None)

                        def _track_user() -> None:
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
                                    (_uid, _uname, _fname, _lname, now_str, now_str)
                                )

                        import asyncio
                        await asyncio.to_thread(_track_user)
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
