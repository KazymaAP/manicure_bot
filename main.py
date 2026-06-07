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

    # FIXED BUG-14: явная проверка наличия администраторов при запуске
    if not settings.admin_ids:
        logger.warning(
            "⚠️ КРИТИЧЕСКОЕ ПРЕДУПРЕЖДЕНИЕ: ADMIN_IDS не настроены или содержат placeholder! "
            "Ни один пользователь не имеет доступа к admin-панели (/admin). "
            "Установите ADMIN_IDS=ваш_telegram_id в .env"
        )

    # ── Хранилище FSM ─────────────────────────────────────────────────────
    # FIXED BUG-11: При отсутствии Redis используем MemoryStorage с предупреждением.
    # В production MemoryStorage НЕ рекомендуется — при перезапуске бота все
    # FSM-состояния пользователей теряются (пользователи в процессе записи получают
    # «зависший» диалог). Для production установите REDIS_URL в .env.
    if settings.redis_url:
        try:
            from aiogram.fsm.storage.redis import RedisStorage
            storage = RedisStorage.from_url(
                settings.redis_url,
                state_ttl=3600,   # FIXED BUG-11: TTL 1 час для FSM-состояний
                data_ttl=86400,   # FIXED BUG-11: TTL 24 часа для FSM-данных
            )
            logger.info("FSM Storage: Redis (%s) с TTL state=1h, data=24h", settings.redis_url)
        except ImportError:
            logger.warning(
                "redis пакет не установлен, используем MemoryStorage. "
                "⚠️ ВНИМАНИЕ: В production используйте Redis (REDIS_URL в .env)!"
            )
            storage = MemoryStorage()
        except Exception as exc:
            logger.warning("Ошибка подключения к Redis (%s): %s. Используем MemoryStorage.", settings.redis_url, exc)
            storage = MemoryStorage()
    else:
        storage = MemoryStorage()
        # FIXED BUG-11: явное предупреждение в логах о production-ограничении MemoryStorage
        logger.warning(
            "FSM Storage: MemoryStorage. ⚠️ ВНИМАНИЕ: Состояния теряются при перезапуске! "
            "Для production установите REDIS_URL в .env файле."
        )

    # ── Бот и диспетчер ───────────────────────────────────────────────────
    bot = Bot(
        # FIXED H-3: SecretStr — получаем реальное значение через get_secret_value()
        token=settings.bot_token.get_secret_value(),
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
    # FIXED: передаём container в data для middleware (трекинг пользователей)
    dp["container"] = container
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
    final_router = setup_final_features_router(container)
    dp.include_router(final_router)

    # ── Планировщик напоминаний ───────────────────────────────────────────
    reminder_service = container.reminder_service
    reminder_service.start()
    reminder_service.restore_reminders()
    # FIXED BUG-4: загружаем список заблокировавших пользователей из БД в кэш памяти.
    # Это гарантирует что после перезапуска бота заблокировавшие пользователи
    # не получают уведомления (без необходимости ждать Forbidden-ошибки снова).
    try:
        container.notification_service.load_blocked_from_db()
    except Exception as _e:
        logger.warning("Failed to load blocked users from DB: %s", _e)
    # FIXED BUG-03: регистрируем задачи ТОЛЬКО в одном месте (в ReminderService).
    # Ранее archive и insufficient_slots регистрировались ДВАЖДЫ:
    #   1) через reminder_service.schedule_weekly_archive() / schedule_insufficient_slots_check()
    #   2) через final_router.register_scheduled_jobs() с ДРУГИМИ функциями и ID.
    # Итог: оба набора выполнялись параллельно. Теперь — единственный источник задач.
    # final_router.register_scheduled_jobs() УДАЛЁН — его задачи продублированы в ReminderService.
    reminder_service.schedule_daily_digest(hour=9, minute=0)   # 9:00 UTC
    reminder_service.schedule_daily_backup(hour=2, minute=0)   # 2:00 UTC
    reminder_service.schedule_weekly_archive(hour=3, minute=0) # Вс 3:00 UTC
    reminder_service.schedule_insufficient_slots_check(hour=10, minute=0)  # 10:00 UTC
    # NOTE: final_router.register_scheduled_jobs() НЕ вызывается — задачи уже зарегистрированы выше.
    logger.info("Планировщик напоминаний запущен")

    # ── Health Server (для мониторинга) ────────────────────────────────────
    health_server = None
    try:
        from src.infrastructure.http.health_server import HealthServer

        # FIXED H-04: используем settings.health_port вместо небезопасного os.getenv()
        # FIXED C-5: передаём metrics_token для защиты /metrics эндпоинта
        # FIXED H-8: биндимся на 127.0.0.1 (только локально) для безопасности
        health_server = HealthServer(
            appointment_service=container.appointment_service,
            port=settings.health_port,
            metrics_token=settings.metrics_token,
            bind_host="127.0.0.1",
        )
        await health_server.setup()
    except ImportError:
        logger.warning("aiohttp not available, health server disabled")
    except Exception as exc:
        logger.warning("Failed to start health server: %s", exc)

    # ── Запуск polling ────────────────────────────────────────────────────
    try:
        # FIXED: удалён мёртвый webhook код
        # Webhook режим не реализован. Используем polling для совместимости.
        # Для webhook режима нужна отдельная реализация с aiohttp/FastAPI сервером.
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Бот запущен. Ожидаю обновления…")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())  # type: ignore[arg-type]
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
