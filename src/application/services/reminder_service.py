"""
src/application/services/reminder_service.py — Сервис напоминаний.

✅ Из v2_tar: AsyncIOScheduler, schedule/cancel/restore_reminders
✅ Улучшения v4: hours_before параметр, misfire_grace_time, лучшее логирование
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from src.application.services.appointment_service import AppointmentService

if TYPE_CHECKING:
    from src.application.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

_JOB_PREFIX = "reminder_"


class ReminderService:
    """Сервис управления напоминаниями через APScheduler.

    FIXED: использует SQLAlchemyJobStore+SQLite при наличии зависимостей (персистентность jobs),
    datetime — timezone-aware (UTC), и явная диагностическая ошибка при отсутствии APScheduler/SQLAlchemy.
    """

    def __init__(
        self,
        appointment_service: AppointmentService,
        notification_service: NotificationService,
        hours_before: int = 24,
        jobstore_url: str | None = None,
        admin_ids: list[int] | None = None,
        backup_service: Any | None = None,
    ) -> None:
        self._appointment_service = appointment_service
        self._notification_service = notification_service
        self._hours_before = hours_before
        self._admin_ids = admin_ids or []
        self._backup_service = backup_service

        # Инициализация планировщика: предпочитаем SQLAlchemyJobStore (персистентность), иначе MemoryJobStore
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore
            from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore  # type: ignore
        except Exception as exc:
            # FIXED: понятная ошибка при отсутствии APScheduler/SQLAlchemy
            raise RuntimeError(
                "APScheduler with SQLAlchemy support is required for persistent reminders. Install with: pip install apscheduler[sqlalchemy]"
            ) from exc

        jobstores = {}
        if jobstore_url:
            jobstores = {"default": SQLAlchemyJobStore(url=jobstore_url)}
        else:
            # fallback — volatile, но предупредим в логах
            from apscheduler.jobstores.memory import MemoryJobStore  # type: ignore

            logger.warning("No jobstore_url provided — falling back to in-memory jobstore (reminders won't survive restarts)")
            jobstores = {"default": MemoryJobStore()}

        self._scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            job_defaults={
                "misfire_grace_time": 3600,  # 1 час допустимого опоздания
                "coalesce": True,
            },
        )

    def start(self) -> None:
        self._scheduler.start()
        logger.info("ReminderService scheduler started.")

    def shutdown(self) -> None:
        try:
            if getattr(self._scheduler, "running", False):
                self._scheduler.shutdown(wait=False)
        finally:
            logger.info("ReminderService scheduler stopped.")

    def schedule_reminder(
        self,
        appointment_id: int,
        user_id: int,
        date_str: str,
        time_str: str,
    ) -> None:
        # Время визита в UTC (naive -> считаем как локальное время и переводим в UTC)
        from datetime import timezone

        appt_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        # Привязываем к UTC — FIXED: используем timezone-aware datetime
        appt_dt = appt_dt.replace(tzinfo=timezone.utc)
        now = datetime.now(tz=timezone.utc)
        # Планируем несколько напоминаний: основной self._hours_before и дополнительные 2h и 1h
        hours_set = {int(self._hours_before), 2, 1}
        for hrs in sorted(hours_set, reverse=True):
            remind_at = appt_dt - timedelta(hours=hrs)
            if remind_at <= now:
                logger.debug("Skipping reminder %dh for appointment #%s as it's in the past", hrs, appointment_id)
                continue
            job_id = f"{_JOB_PREFIX}{appointment_id}_{hrs}"
            self._scheduler.add_job(
                self._send_reminder_job,
                trigger="date",
                run_date=remind_at,
                args=[user_id, time_str, appointment_id],
                id=job_id,
                replace_existing=True,
            )
            logger.info("Reminder (%dh) scheduled for appointment #%s at %s UTC", hrs, appointment_id, remind_at)

    def cancel_reminder(self, appointment_id: int) -> None:
        job_id = f"{_JOB_PREFIX}{appointment_id}"
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)
            logger.info("Reminder cancelled for appointment #%s", appointment_id)

    def restore_reminders(self) -> None:
        appointments = self._appointment_service.get_upcoming_unreminded()
        restored = 0
        for appt in appointments:
            if appt.id is None:
                logger.warning("Skipping scheduling reminder for appointment without id: %s", appt)
                continue
            try:
                self.schedule_reminder(
                    appointment_id=appt.id,
                    user_id=appt.user_id,
                    date_str=appt.date,
                    time_str=appt.time,
                )
                restored += 1
            except Exception:
                logger.exception("Failed to restore reminder for appointment %s", appt.id)
        logger.info("Restored %d reminder jobs from DB.", restored)

    async def _send_reminder_job(
        self,
        user_id: int,
        time_str: str,
        appointment_id: int,
    ) -> None:
        await self._notification_service.send_reminder(user_id, time_str, appointment_id)

    def schedule_daily_digest(self, hour: int = 9, minute: int = 0) -> None:
        """Планирует ежедневный дайджест администратору в указанное время (UTC).

        FIXED: рассылка сводки администратору каждое утро в 9:00 UTC.
        """
        from apscheduler.triggers.cron import CronTrigger  # type: ignore

        job_id = "daily_digest"
        self._scheduler.add_job(
            self._daily_digest_job,
            trigger=CronTrigger(hour=hour, minute=minute),
            id=job_id,
            replace_existing=True,
        )
        logger.info("Daily digest scheduled at %02d:%02d UTC", hour, minute)

    def schedule_daily_backup(self, hour: int = 2, minute: int = 0) -> None:
        """Планирует ежедневный бэкап БД в указанное время (UTC).

        FIXED: автоматический бэкап с ротацией каждый день в 2:00 UTC.
        """
        from apscheduler.triggers.cron import CronTrigger  # type: ignore

        if not self._backup_service:
            logger.warning("BackupService not provided, skipping backup scheduling")
            return
        job_id = "daily_backup"
        self._scheduler.add_job(
            self._daily_backup_job,
            trigger=CronTrigger(hour=hour, minute=minute),
            id=job_id,
            replace_existing=True,
        )
        logger.info("Daily backup scheduled at %02d:%02d UTC", hour, minute)

    async def _daily_digest_job(self) -> None:
        """Отправляет ежедневный дайджест администраторам."""
        try:
            import asyncio
            from src.presentation.formatters.message_formatter import MessageFormatter
            from datetime import date as _date

            stats = await asyncio.to_thread(self._appointment_service.get_statistics)
            today_str = _date.today().isoformat()
            today_appts = await asyncio.to_thread(self._appointment_service.get_by_date, today_str)

            text = (
                "📊 <b>Ежедневный дайджест</b>\n\n"
                f"📋 Всего записей: <b>{stats.get('total', 0)}</b>\n"
                f"✅ Активных: <b>{stats.get('confirmed', 0)}</b>\n"
                f"❌ Отменено: <b>{stats.get('cancelled', 0)}</b>\n\n"
                f"📅 <b>Сегодня ({today_str}):</b> <b>{len(today_appts)}</b> записей\n"
            )

            for appt in today_appts:
                text += f"  • {appt.time} — {appt.client_name} ({appt.phone})\n"

            for admin_id in self._admin_ids:
                try:
                    await self._notification_service.bot.send_message(admin_id, text, parse_mode="HTML")
                except Exception as exc:
                    logger.warning("Failed to send digest to admin %s: %s", admin_id, exc)
        except Exception:
            logger.exception("Daily digest job failed")

    async def _daily_backup_job(self) -> None:
        """Создаёт ежедневный бэкап БД."""
        try:
            if not self._backup_service:
                logger.warning("BackupService not available")
                return
            backup_path = await __import__("asyncio").to_thread(self._backup_service.create_backup)
            if backup_path:
                logger.info("Daily backup completed: %s", backup_path)
        except Exception:
            logger.exception("Daily backup job failed")
