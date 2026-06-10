"""
src/presentation/middlewares/admin_middleware.py — Middleware для проверки прав администратора.

FIX #12: устраняет дублирование проверки _is_admin() в каждом хендлере.
Предназначен для использования на отдельных роутерах, где все хендлеры
должны быть доступны только администраторам.

Использование (опционально — уже есть _is_admin() во всех хендлерах):
    router.callback_query.middleware(AdminOnlyMiddleware(settings.admin_ids))
    router.message.middleware(AdminOnlyMiddleware(settings.admin_ids))
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Awaitable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

logger = logging.getLogger(__name__)


class AdminOnlyMiddleware(BaseMiddleware):
    """Middleware, блокирующий доступ не-администраторам к хендлерам роутера.

    FIX #12: централизованная проверка прав вместо дублирующего кода
    в каждом хендлере. При добавлении нового хендлера на admin-роутер
    проверка применяется автоматически.
    """

    def __init__(self, admin_ids: list[int]) -> None:
        self.admin_ids = set(admin_ids)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Проверяет права перед передачей управления хендлеру."""
        from_user = getattr(event, 'from_user', None)
        if from_user is None or from_user.id not in self.admin_ids:
            # Для CallbackQuery — отвечаем чтобы убрать loading-индикатор
            if isinstance(event, CallbackQuery):
                await event.answer("Нет прав администратора.", show_alert=True)
            return None
        return await handler(event, data)
