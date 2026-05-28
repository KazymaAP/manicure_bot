# main.py — точка входа бота (v4)
"""Точка входа: инициализация бота, диспетчера, планировщика и запуск polling."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from src.config.settings import Settings, get_settings
from src.config.logging_config import setup_logging
from src.config.dependencies import Container

from src.presentation.handlers.common_handler import setup_common_router
from src.presentation.handlers.user_handler import setup_user_router
from src.presentation.handlers.admin_handler import setup_admin_router
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
    dp.message.middleware(LoggingMiddleware())
    dp.callback_query.middleware(LoggingMiddleware())

    # ── Роутеры ───────────────────────────────────────────────────────────
    dp.include_router(setup_common_router(container))
    dp.include_router(setup_user_router(container))
    dp.include_router(setup_admin_router(container))

    # ── Планировщик напоминаний ───────────────────────────────────────────
    reminder_service = container.reminder_service
    reminder_service.start()
    reminder_service.restore_reminders()
    logger.info("Планировщик напоминаний запущен")

    # ── Запуск polling ────────────────────────────────────────────────────
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Бот запущен. Ожидаю обновления…")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        # Грамотно останавливаем сервис напоминаний и ресурсы контейнера
        try:
            reminder_service.shutdown()
        except Exception:
            pass
        await container.shutdown()
        await bot.session.close()
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    asyncio.run(main())
