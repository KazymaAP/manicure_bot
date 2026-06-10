from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger(__name__)

# Максимальный размер словаря бакетов (защита от утечки памяти)
_MAX_BUCKETS = 10_000
# Интервал очистки устаревших бакетов (секунды)
_CLEANUP_INTERVAL = 300  # 5 минут


class RateLimitMiddleware(BaseMiddleware):
    """Простой rate-limit middleware per-user.

    FIXED: предотвращает всплески от одного пользователя.
    FIXED: используем deque вместо list для O(1) операций pop из начала.
    FIXED: ограничен размер словаря бакетов (_MAX_BUCKETS) для защиты памяти.
    FIXED: убран asyncio.Lock на весь хэндлер — не нужен при deque + per-user scope.
    FIXED H-01: добавлена периодическая очистка устаревших бакетов для предотвращения
    утечки памяти при долгой работе бота.
    """

    def __init__(self, calls: int = 5, per_seconds: int = 5) -> None:
        super().__init__()
        self.calls = calls
        self.per_seconds = per_seconds
        # FIXED: deque вместо list — O(1) удаление из начала
        self._buckets: dict[int, deque[float]] = defaultdict(deque)
        # FIXED H-01: время последней очистки для периодической очистки устаревших бакетов
        self._last_cleanup: float = time.time()

    async def __call__(  # type: ignore[override]
        self,
        handler: Any,
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id = None
        try:
            # FIXED BUG-08: в aiogram 3.x event в middleware уже является конкретным типом
            # (Message, CallbackQuery и т.д.), а не Update. Используем isinstance() для
            # правильного извлечения user_id вместо неработающего update.message.from_user.id.
            if isinstance(event, Message | CallbackQuery):
                if event.from_user is not None:
                    user_id = event.from_user.id
            else:
                # Для прочих типов (InlineQuery и т.д.) пробуем через from_user напрямую
                from_user = getattr(event, "from_user", None)
                if from_user is not None:
                    user_id = getattr(from_user, "id", None)
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

        # FIXED H-01: периодическая очистка устаревших бакетов.
        # Удаляем бакеты, в которых нет записей за последние per_seconds секунд.
        # Это предотвращает бесконечный рост словаря при долгой работе бота
        # (ранее пустые deque оставались в памяти навсегда после того, как пользователи замолкали).
        if now - self._last_cleanup > _CLEANUP_INTERVAL:
            cutoff = now - self.per_seconds
            stale_keys = [uid for uid, bkt in self._buckets.items() if not bkt or bkt[-1] < cutoff]
            for uid in stale_keys:
                del self._buckets[uid]
            self._last_cleanup = now
            if stale_keys:
                logger.debug("RateLimitMiddleware: cleaned up %d stale buckets", len(stale_keys))

        # FIXED BUG-02: ограничиваем размер словаря бакетов для защиты от утечки памяти.
        # Проверка ПОСЛЕ bucket.append(now) — удаляем СТОЛЬКО элементов, сколько нужно,
        # чтобы вернуться к лимиту (а не только один, как было раньше).
        # Это гарантирует что len(self._buckets) никогда не превысит _MAX_BUCKETS.
        while len(self._buckets) > _MAX_BUCKETS:
            oldest_uid = next(iter(self._buckets))
            del self._buckets[oldest_uid]

        return await handler(event, data)
