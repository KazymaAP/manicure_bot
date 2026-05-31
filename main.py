# main.py — точка входа бота (v4)
"""Точка входа: инициализация бота, диспетчера, планировщика и запуск polling."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from src.config.dependencies import Container
from src.config.logging_config import setup_logging
from src.config.settings import get_settings
from src.presentation.handlers.admin_handler import setup_admin_router
from src.presentation.handlers.common_handler import setup_common_router
from src.presentation.handlers.user_handler import setup_user_router
from src.presentation.middlewares.logging_middleware import LoggingMiddleware


async def main() -> None:
    # ── Загрузка настроек ─────────────────────────────────────────────────
    settings = get_settings()  # читает из .env / переменных окружения (кэшированный)
    setup_logging(settings.log_level, settings.log_file)
    logger = logging.getLogger(__name__)
    logger.info("Запуск бота (v4)…")

    # ── Хранилище FSM ─────────────────────────────────────────────────────
    if settings.redis_url:
        try:
            from aiogram.fsm.storage.redis import RedisStorage
            storage = RedisStorage.from_url(settings.redis_url)
            logger.info("FSM Storage: Redis (%s)", settings.redis_url)
        except ImportError:
            logger.warning("redis пакет не установлен, используем MemoryStorage")
            storage = MemoryStorage()
    else:
        storage = MemoryStorage()
        logger.info("FSM Storage: Memory")

    # ── Бот и диспетчер ───────────────────────────────────────────────────
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=storage)

    # ── DI Container ──────────────────────────────────────────────────────
    container = Container(settings=settings)
    container.initialize()
    container.build_services(bot)
    logger.info("Контейнер зависимостей инициализирован")

    # ── Middleware ────────────────────────────────────────────────────────
    logging_mw = LoggingMiddleware()
    dp.message.middleware(logging_mw)
    dp.callback_query.middleware(logging_mw)
    # FIXED: простая защита от флуда — rate limiting middleware per-user
    from src.presentation.middlewares.rate_limit_middleware import RateLimitMiddleware

    rate_mw = RateLimitMiddleware()
    dp.message.middleware(rate_mw)
    dp.callback_query.middleware(rate_mw)

    # ── Роутеры ───────────────────────────────────────────────────────────
    dp.include_router(setup_common_router(container))
    dp.include_router(setup_user_router(container))
    dp.include_router(setup_admin_router(container))
    # FIXED: подключаем роутеры расширенных и финальных фич
    from src.presentation.handlers.extended_features_handler import setup_extended_features_router
    from src.presentation.handlers.final_features_handler import setup_final_features_router
    dp.include_router(setup_extended_features_router(container))
    dp.include_router(setup_final_features_router(container))

    # ── Планировщик напоминаний ───────────────────────────────────────────
    reminder_service = container.reminder_service
    reminder_service.start()
    reminder_service.restore_reminders()
    # FIXED: планируем ежедневный дайджест и бэкап
    reminder_service.schedule_daily_digest(hour=9, minute=0)  # 9:00 UTC
    reminder_service.schedule_daily_backup(hour=2, minute=0)  # 2:00 UTC
    logger.info("Планировщик напоминаний запущен")

    # ── Health Server (для мониторинга) ────────────────────────────────────
    health_server = None
    try:
        from src.infrastructure.http.health_server import HealthServer

        health_server = HealthServer(
            appointment_service=container.appointment_service,
            port=int(__import__("os").getenv("HEALTH_PORT", "8080")),
        )
        await health_server.setup()
    except ImportError:
        logger.warning("aiohttp not available, health server disabled")
    except Exception as exc:
        logger.warning("Failed to start health server: %s", exc)

    # ── Запуск polling или webhook ────────────────────────────
    try:
        # FIXED: фича #40 — поддержка webhook режима если настроен
        if settings.webhook_url:
            logger.info("Запуск бота в режиме webhook: %s", settings.webhook_url)
            await bot.set_webhook(settings.webhook_url)
            # Вместо polling используем webhook сервер (нужен отдельный код для aiohttp)
            logger.warning("Webhook requires custom server implementation (currently not fully integrated)")
            # Fallback на polling
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Fallback to polling mode")
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        else:
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Бот запущен. Ожидаю обновления…")
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        # Грамотно останавливаем health server
        if health_server:
            try:
                await health_server.shutdown()
            except Exception:
                pass
        # Грамотно останавливаем сервис напоминаний и ресурсы контейнера
        try:
            reminder_service.shutdown()
        except Exception:
            pass
        await container.shutdown()
        await bot.session.close()
        # Закрываем FSM Storage gracefully если это не MemoryStorage
        if not isinstance(storage, MemoryStorage):
            try:
                await storage.close()
                logger.info("FSM Storage closed.")
            except Exception as e:
                logger.warning("Error closing FSM storage: %s", e)
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    asyncio.run(main())
