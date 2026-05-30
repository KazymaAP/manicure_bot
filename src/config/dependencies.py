"""
src/config/dependencies.py — DI-контейнер приложения.

✅ Из v2_tar: Container pattern, build_services, register_middlewares_and_data
✅ Улучшения v4: явные type-hints, lazy initialization, graceful shutdown
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

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
        self._appointment_service = AppointmentService(
            appointment_repo=self._appointment_repo,
            schedule_repo=self._schedule_repo,
            max_per_user=self._settings.max_appointments_per_user,
        )
        # Загружаем service_name из config.json
        import json
        import os
        _config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config.json")
        try:
            with open(_config_path, encoding="utf-8") as _f:
                _cfg = json.load(_f)
            _service_name = _cfg.get("bot", {}).get("service_name", "маникюр")
        except Exception:
            _service_name = "маникюр"

        self._schedule_service = ScheduleService(
            schedule_repo=self._schedule_repo,
            days_ahead=self._settings.schedule_days_ahead,
        )
        self._notification_service = NotificationService(
            bot=bot,
            admin_ids=self._settings.admin_ids,
            schedule_channel_id=self._settings.schedule_channel_id,
            appointment_repo=self._appointment_repo,
            service_name=_service_name,
        )
        self._reminder_service = ReminderService(
            appointment_service=self._appointment_service,
            notification_service=self._notification_service,
            hours_before=self._settings.reminder_hours_before,
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
