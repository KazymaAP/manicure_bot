"""
src/config/dependencies.py — DI-контейнер приложения.

✅ Из v2_tar: Container pattern, build_services, register_middlewares_and_data
✅ Улучшения v4: явные type-hints, lazy initialization, graceful shutdown
"""
from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aiogram import Bot

from src.application.services.appointment_service import AppointmentService
from src.application.services.notification_service import NotificationService
from src.application.services.reminder_service import ReminderService
from src.application.services.schedule_service import ScheduleService
from src.config.settings import Settings
from src.infrastructure.database.connection import DatabaseManager
from src.infrastructure.repositories.appointment_repository import AppointmentRepository
from src.infrastructure.repositories.schedule_repository import ScheduleRepository

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_config_json() -> dict:
    """Загружает и кэширует config.json (читается один раз при запуске).

    Returns:
        Словарь конфигурации из config.json.
    """
    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config.json")
    try:
        with open(config_path, encoding="utf-8") as f:
            # BAG-19 FIX: явный тип, чтобы mypy не ругался на Any из json.load
            config: dict[str, Any] = json.load(f)
        logger.debug("Config loaded from %s", config_path)
        return config
    except FileNotFoundError:
        logger.warning("config.json not found at %s, using defaults", config_path)
        return {}
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in config.json: %s", e)
        return {}


class Container:
    """DI-контейнер для управления зависимостями приложения.

    Создаёт и хранит единственные экземпляры всех сервисов.
    Паттерн IoC Container с ленивой инициализацией.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._db: DatabaseManager | None = None
        self._appointment_repo: AppointmentRepository | None = None
        self._schedule_repo: ScheduleRepository | None = None
        self._appointment_service: AppointmentService | None = None
        self._schedule_service: ScheduleService | None = None
        self._notification_service: NotificationService | None = None
        self._reminder_service: ReminderService | None = None

    def initialize_db(self) -> None:
        """Инициализирует базу данных и создаёт схему таблиц."""
        self._db = DatabaseManager(self._settings.db_path)
        self._db.initialize_schema()
        logger.info("Database initialized at: %s", self._settings.db_path)

    def initialize(self) -> None:
        """Инициализирует контейнер (база данных). Синхронный метод."""
        self.initialize_db()

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def db(self) -> DatabaseManager:
        if self._db is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self._db

    def build_services(self, bot: Bot) -> None:
        """Создаёт все сервисы приложения.

        Должен вызываться ПОСЛЕ initialize_db().

        Args:
            bot: Инициализированный экземпляр Telegram бота.

        Raises:
            RuntimeError: Если initialize_db() не был вызван.
        """
        if not self._db:
            raise RuntimeError("Call initialize_db() before build_services()")

        # Репозитории
        self._appointment_repo = AppointmentRepository(self._db)
        self._schedule_repo = ScheduleRepository(self._db)

        # Сервисы (порядок важен: notification нужен для reminder)
        # Подготовим mapping name->duration (минутах) для AppointmentService
        service_durations = {}
        for name, info in (self._settings.services or {}).items():
            try:
                if isinstance(info, dict):
                    duration = int(info.get("duration", 0))
                elif isinstance(info, int):
                    duration = info
                else:
                    logger.warning(
                        "Unexpected type for service %r info: %s, expected dict or int",
                        name, type(info).__name__,
                    )
                    duration = 0
            except Exception:
                duration = 0
            service_durations[name] = duration

        # Загружаем service_name из config.json (кэшированный)
        config = _load_config_json()
        service_name = config.get("bot", {}).get("service_name", "маникюр")

        self._schedule_service = ScheduleService(
            schedule_repo=self._schedule_repo,
            days_ahead=self._settings.schedule_days_ahead,
            default_time_slots=self._settings.default_time_slots,
        )
        self._notification_service = NotificationService(
            bot=bot,
            admin_ids=self._settings.admin_ids,
            schedule_channel_id=self._settings.schedule_channel_id,
            appointment_repo=self._appointment_repo,
            service_name=service_name,
            # FIXED M-06: передаём адрес студии из settings, чтобы он отображался в напоминаниях
            address=self._settings.address or "",
        )

        # FIXED: создаём AppointmentService с callback для отправки уведомлений waitlist
        # FIXED M-06: хранилище ссылок на fire-and-forget таски — без этого GC может удалить таск до завершения
        _pending_tasks: set = set()

        def notify_waitlist_available(user_id: int, date: str, time: str) -> None:
            """Callback для отправки уведомлений пользователям из waitlist о свободных слотах.

            FIXED M-06: сохраняем ссылку на таск в _pending_tasks чтобы GC не удалил его до завершения.
            """
            import asyncio
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                # Нет running loop — в тесте или в синхронном контексте
                return
            # Создаём таск и сохраняем ссылку
            task = asyncio.create_task(
                self._notification_service.notify_waitlist_slot_available(user_id, date, time)
            )
            _pending_tasks.add(task)
            # Автоматически удаляем ссылку после завершения
            task.add_done_callback(_pending_tasks.discard)

        self._appointment_service = AppointmentService(
            appointment_repo=self._appointment_repo,
            schedule_repo=self._schedule_repo,
            max_per_user=self._settings.max_appointments_per_user,
            service_durations=service_durations,
            notification_callback=notify_waitlist_available,
        )

        # FIXED: создаём BackupService
        from src.application.services.backup_service import BackupService
        backup_service = BackupService(
            db_path=self._settings.db_path,
            backup_dir="data/backups",
            keep_count=7,
        )

        # Создаём ReminderService. В локальном запуске используем in-memory jobstore
        # чтобы избежать проблем с сериализацией bound-methods при сохранении в SQLite.
        # Для персистентности в продакшне задайте JOBSTORE_PERSISTENT=true и реализуйте
        # соответствующую логику при деплое.
        jobstore_url = None

        # FIXED C-06: передаём timezone для корректного расчёта времени напоминаний
        # FIXED BUG-H2: передаём schedule_service напрямую, чтобы ReminderService
        # не нарушал инкапсуляцию через getattr(_schedule_repo)
        self._reminder_service = ReminderService(
            appointment_service=self._appointment_service,
            notification_service=self._notification_service,
            hours_before=self._settings.reminder_hours_before,
            jobstore_url=jobstore_url,
            admin_ids=self._settings.admin_ids,
            backup_service=backup_service,
            timezone=self._settings.timezone,
            schedule_service=self._schedule_service,
        )
        logger.info("All services built successfully.")

    @property
    def appointment_service(self) -> AppointmentService:
        if self._appointment_service is None:
            raise RuntimeError("Services not built. Call build_services() first.")
        return self._appointment_service

    @property
    def schedule_service(self) -> ScheduleService:
        if self._schedule_service is None:
            raise RuntimeError("Services not built. Call build_services() first.")
        return self._schedule_service

    @property
    def notification_service(self) -> NotificationService:
        if self._notification_service is None:
            raise RuntimeError("Services not built. Call build_services() first.")
        return self._notification_service

    @property
    def reminder_service(self) -> ReminderService:
        if self._reminder_service is None:
            raise RuntimeError("Services not built. Call build_services() first.")
        return self._reminder_service

    async def shutdown(self) -> None:
        """Очищает ресурсы контейнера при завершении."""
        if self._db:
            await self._db.close()
            logger.info("Database connection closed.")
