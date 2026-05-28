"""
src/application/services/reminder_service.py — Сервис напоминаний.

✅ Из v2_tar: AsyncIOScheduler, schedule/cancel/restore_reminders
✅ Улучшения v4: hours_before параметр, misfire_grace_time, лучшее логирование
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

# APScheduler stubs may be missing in some environments - silence type checkers and annotate scheduler as Any
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore
    from apscheduler.jobstores.memory import MemoryJobStore  # type: ignore
except Exception:
    AsyncIOScheduler = object
    MemoryJobStore = object

from src.application.services.appointment_service import AppointmentService

if TYPE_CHECKING:
    from src.application.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

_JOB_PREFIX = "reminder_"


class ReminderService:
    """Сервис управления напоминаниями через APScheduler.

    Планирует, отменяет и восстанавливает задачи отправки напоминаний
    за N часов до записи (по умолчанию 24 часа).
    """

    def __init__(
        self,
        appointment_service: AppointmentService,
        notification_service: "NotificationService",
        hours_before: int = 24,
    ) -> None:
        """Инициализирует сервис.

        Args:
            appointment_service: Сервис работы с записями.
            notification_service: Сервис отправки уведомлений.
            hours_before: За сколько часов до записи слать напоминание.
        """
        self._appointment_service = appointment_service
        self._notification_service = notification_service
        self._hours_before = hours_before
        # Annotate scheduler as Any to avoid type issues when stubs are missing
        self._scheduler: Any = AsyncIOScheduler(
            jobstores={"default": MemoryJobStore()},
            job_defaults={
                "misfire_grace_time": 3600,  # 1 час допустимого опоздания
                "coalesce": True,
            },
        )

    def start(self) -> None:
        """Запускает планировщик."""
        self._scheduler.start()
        logger.info("ReminderService scheduler started.")

    def shutdown(self) -> None:
        """Останавливает планировщик."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        logger.info("ReminderService scheduler stopped.")

    def schedule_reminder(
        self,
        appointment_id: int,
        user_id: int,
        date_str: str,
        time_str: str,
    ) -> None:
        """Планирует отправку напоминания.

        Args:
            appointment_id: ID записи.
            user_id: Telegram ID клиента.
            date_str: Дата записи «YYYY-MM-DD».
            time_str: Время записи «HH:MM».
        """
        appt_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        remind_at = appt_dt - timedelta(hours=self._hours_before)
        now = datetime.now()

        if remind_at <= now:
            logger.info(
                "Appointment #%s: less than %dh until visit, skipping reminder.",
                appointment_id, self._hours_before,
            )
            return

        job_id = f"{_JOB_PREFIX}{appointment_id}"
        self._scheduler.add_job(
            self._send_reminder_job,
            trigger="date",
            run_date=remind_at,
            args=[user_id, time_str, appointment_id],
            id=job_id,
            replace_existing=True,
        )
        logger.info(
            "Reminder scheduled for appointment #%s at %s",
            appointment_id, remind_at,
        )

    def cancel_reminder(self, appointment_id: int) -> None:
        """Отменяет запланированное напоминание.

        Args:
            appointment_id: ID записи.
        """
        job_id = f"{_JOB_PREFIX}{appointment_id}"
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)
            logger.info("Reminder cancelled for appointment #%s", appointment_id)

    def restore_reminders(self) -> None:
        """Восстанавливает напоминания из БД после перезапуска бота.

        Загружает все предстоящие записи без отправленных напоминаний
        и планирует задачи для них.
        """
        appointments = self._appointment_service.get_upcoming_unreminded()
        restored = 0
        for appt in appointments:
            if appt.id is None:
                logger.warning("Skipping scheduling reminder for appointment without id: %s", appt)
                continue
            self.schedule_reminder(
                appointment_id=appt.id,
                user_id=appt.user_id,
                date_str=appt.date,
                time_str=appt.time,
            )
            restored += 1
        logger.info("Restored %d reminder jobs from DB.", restored)

    async def _send_reminder_job(
        self,
        user_id: int,
        time_str: str,
        appointment_id: int,
    ) -> None:
        """Задача APScheduler: отправка напоминания.

        Args:
            user_id: Telegram ID клиента.
            time_str: Время записи.
            appointment_id: ID записи.
        """
        await self._notification_service.send_reminder(user_id, time_str, appointment_id)
