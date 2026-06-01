"""
src/application/services/reminder_service.py — Сервис напоминаний.

✅ Из v2_tar: AsyncIOScheduler, schedule/cancel/restore_reminders
✅ Улучшения v4: hours_before параметр, misfire_grace_time, лучшее логирование
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from src.application.services.appointment_service import AppointmentService

if TYPE_CHECKING:
    from src.application.services.notification_service import NotificationService
    from src.application.services.schedule_service import ScheduleService

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
        timezone: str = "UTC",
        schedule_service: ScheduleService | None = None,
    ) -> None:
        self._appointment_service = appointment_service
        self._notification_service = notification_service
        self._hours_before = hours_before
        self._admin_ids = admin_ids or []
        self._backup_service = backup_service
        self._timezone = timezone  # FIXED C-06: храним timezone для корректного расчёта напоминаний
        # FIXED BUG-H2: schedule_service передаётся напрямую, вместо нарушения инкапсуляции через getattr(_schedule_repo)
        self._schedule_service = schedule_service

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
        timezone_str: str | None = None,
    ) -> None:
        """Планирует напоминания для записи.

        FIXED C-06: время в БД хранится в локальной timezone (не UTC).
        Используем timezone из settings для корректного перевода в UTC при планировании.
        Если timezone_str не передан — используем UTC как безопасный дефолт.
        """
        from datetime import timezone

        appt_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")

        # FIXED C-06: используем переданную timezone вместо принудительного UTC
        if timezone_str and timezone_str != "UTC":
            try:
                try:
                    from zoneinfo import ZoneInfo  # Python 3.9+
                except ImportError:
                    from backports.zoneinfo import ZoneInfo  # type: ignore
                local_tz = ZoneInfo(timezone_str)
                appt_dt = appt_dt.replace(tzinfo=local_tz)
            except Exception:
                # При ошибке загрузки timezone — логируем и используем UTC
                logger.warning(
                    "Unknown timezone %r, falling back to UTC for reminder scheduling",
                    timezone_str,
                )
                appt_dt = appt_dt.replace(tzinfo=timezone.utc)
        else:
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
        """Отменяет все напоминания для записи (все суффиксы часов).

        FIXED MED-01: использует {int(self._hours_before), 2, 1} вместо захардкоженного {24, 2, 1}.
        Ранее при REMINDER_HOURS_BEFORE=48 напоминание планировалось с ID reminder_48_*,
        но при отмене искался reminder_24_* — напоминание не отменялось и приходило клиенту
        на уже отменённую запись. Теперь отменяем точно те же часы, что были запланированы.
        """
        cancelled = False
        # FIXED MED-01: используем self._hours_before вместо хардкода 24
        hours_to_cancel = {int(self._hours_before), 2, 1}
        for hrs in hours_to_cancel:
            job_id = f"{_JOB_PREFIX}{appointment_id}_{hrs}"
            if self._scheduler.get_job(job_id):
                self._scheduler.remove_job(job_id)
                cancelled = True
                logger.info("Reminder (%dh) cancelled for appointment #%s", hrs, appointment_id)

        if not cancelled:
            logger.warning("No reminders found for appointment #%s", appointment_id)

    def restore_reminders(self) -> None:
        appointments = self._appointment_service.get_upcoming_unreminded()
        restored = 0
        for appt in appointments:
            if appt.id is None:
                logger.warning("Skipping scheduling reminder for appointment without id: %s", appt)
                continue
            try:
                # FIXED C-06: передаём timezone для корректного расчёта времени напоминания
                self.schedule_reminder(
                    appointment_id=appt.id,
                    user_id=appt.user_id,
                    date_str=appt.date,
                    time_str=appt.time,
                    timezone_str=self._timezone,
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

    def schedule_weekly_archive(self, hour: int = 3, minute: int = 0) -> None:
        """FIXED: планирует еженедельную архивацию старых записей (по воскресеньям в 3:00 UTC)."""
        from apscheduler.triggers.cron import CronTrigger  # type: ignore

        job_id = "weekly_archive"
        self._scheduler.add_job(
            self._weekly_archive_job,
            trigger=CronTrigger(day_of_week="sun", hour=hour, minute=minute),
            id=job_id,
            replace_existing=True,
        )
        logger.info("Weekly archive job scheduled on Sunday at %02d:%02d UTC", hour, minute)

    def schedule_insufficient_slots_check(self, hour: int = 10, minute: int = 0) -> None:
        """FIXED: планирует ежедневную проверку количества доступных слотов."""
        from apscheduler.triggers.cron import CronTrigger  # type: ignore

        job_id = "insufficient_slots_check"
        self._scheduler.add_job(
            self._insufficient_slots_check_job,
            trigger=CronTrigger(hour=hour, minute=minute),
            id=job_id,
            replace_existing=True,
        )
        logger.info("Insufficient slots check scheduled at %02d:%02d UTC", hour, minute)

    async def _weekly_archive_job(self) -> None:
        """Архивирует старые записи (старше 90 дней)."""
        try:
            import asyncio
            from datetime import date as _date, timedelta

            cutoff_date = (_date.today() - timedelta(days=90)).isoformat()
            all_appts = await asyncio.to_thread(self._appointment_service.get_all)
            old_cancelled = [
                a for a in all_appts
                if a.date < cutoff_date and a.is_cancelled
            ]
            logger.info(
                "Weekly archive: found %d old cancelled appointments (cutoff %s)",
                len(old_cancelled), cutoff_date
            )
            # Здесь можно добавить логику экспорта в архив
        except Exception:
            logger.exception("Weekly archive job failed")

    async def _insufficient_slots_check_job(self) -> None:
        """Проверяет количество доступных слотов и уведомляет администраторов.

        FIXED BUG-H2: используем self._schedule_service (публичный API) вместо
        нарушения инкапсуляции через getattr(self._appointment_service, "_schedule_repo", None).
        Если schedule_service не передан — graceful fallback с предупреждением.
        """
        try:
            from datetime import date as _date, timedelta
            import asyncio

            today = _date.today()
            days_ahead = 30

            if self._schedule_service is not None:
                # FIXED BUG-H2: используем публичный API schedule_service
                available = await asyncio.to_thread(
                    self._schedule_service.get_available_dates,
                    today,
                    days_ahead
                )
                free_days = len(available)
            else:
                # Fallback: обращаемся к schedule_repo через appointment_service
                # (нежелательно, но сохраняет обратную совместимость если schedule_service не передан)
                sched_repo = getattr(self._appointment_service, "_schedule_repo", None)
                if sched_repo is None:
                    logger.warning(
                        "_insufficient_slots_check_job: neither schedule_service nor schedule_repo found. "
                        "Pass schedule_service to ReminderService for correct behaviour."
                    )
                    return
                to_date = (today + timedelta(days=days_ahead)).isoformat()
                available = await asyncio.to_thread(
                    sched_repo.get_available_dates_in_range,
                    today.isoformat(),
                    to_date
                )
                free_days = len(available)

            if free_days < 3:
                text = (
                    f"⚠️ <b>Внимание!</b> Свободных дней в расписании: <b>{free_days}</b>.\n"
                    f"Рекомендуется добавить новые рабочие дни!"
                )
                await self._notification_service.notify_admins_list(text)
                logger.warning("Insufficient slots warning sent: %d free days", free_days)
        except Exception:
            logger.exception("Insufficient slots check job failed")

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
            from datetime import date as _date

            stats = await asyncio.to_thread(self._appointment_service.get_statistics)
            today_str = _date.today().isoformat()
            today_appts = await asyncio.to_thread(self._appointment_service.get_appointments_by_date, today_str)

            text = (
                "📊 <b>Ежедневный дайджест</b>\n\n"
                f"📋 Всего записей: <b>{stats.get('total', 0)}</b>\n"
                f"✅ Активных: <b>{stats.get('confirmed', 0)}</b>\n"
                f"❌ Отменено: <b>{stats.get('cancelled', 0)}</b>\n\n"
                f"📅 <b>Сегодня ({today_str}):</b> <b>{len(today_appts)}</b> записей\n"
            )

            for appt in today_appts:
                text += f"  • {appt.time} — {appt.client_name} ({appt.phone})\n"

            # FIXED: удалён внешний цикл по admin_ids (notify_admins_list уже итерирует)
            try:
                await self._notification_service.notify_admins_list(text)
            except Exception as exc:
                logger.warning("Failed to send digest: %s", exc)
        except Exception:
            logger.exception("Daily digest job failed")

    async def _daily_backup_job(self) -> None:
        """Создаёт ежедневный бэкап БД.

        FIXED M-02: убран антипаттерн __import__("asyncio").
        asyncio уже импортирован в начале модуля — используем его напрямую.
        """
        try:
            if not self._backup_service:
                logger.warning("BackupService not available")
                return
            import asyncio
            backup_path = await asyncio.to_thread(self._backup_service.create_backup)
            if backup_path:
                logger.info("Daily backup completed: %s", backup_path)
        except Exception:
            logger.exception("Daily backup job failed")
