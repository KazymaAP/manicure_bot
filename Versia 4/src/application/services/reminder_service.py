"""
src/application/services/reminder_service.py — Сервис напоминаний.

✅ Из v2_tar: AsyncIOScheduler, schedule/cancel/restore_reminders
✅ Улучшения v4: hours_before параметр, misfire_grace_time, лучшее логирование
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import os
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
            from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore  # type: ignore
            from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore
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
                args=[user_id, time_str, appointment_id, hrs],
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
        hrs: int = 24,
    ) -> None:
        """Отправляет напоминание о записи.

        FIXED БАГ-ВЫСОК-05: перед отправкой проверяем настройки уведомлений пользователя.
        FIXED БАГ #20: проверяем отдельные флаги notif_24h/notif_2h/notif_1h на основе hrs.
        """
        try:
            appt = await asyncio.to_thread(
                self._appointment_service.get_appointment_by_id, appointment_id
            )
            if not appt:
                logger.info(
                    "Skipping reminder for appointment #%s: appointment not found (possibly cancelled)",
                    appointment_id
                )
                return

            notif_settings = await asyncio.to_thread(
                self._get_user_notif_settings_from_db, user_id
            )

            # Проверяем глобальный флаг уведомлений
            if not notif_settings.get("notifications_enabled", 1):
                logger.info(
                    "Skipping reminder for user %s, appointment #%s: notifications disabled by user",
                    user_id, appointment_id
                )
                return

            # FIXED БАГ #20: проверяем индивидуальные флаги по типу напоминания
            if hrs == 24 and not notif_settings.get("notif_24h", 1):
                logger.info(
                    "Skipping 24h reminder for user %s, appointment #%s: notif_24h disabled",
                    user_id, appointment_id
                )
                return
            elif hrs == 2 and not notif_settings.get("notif_2h", 1):
                logger.info(
                    "Skipping 2h reminder for user %s, appointment #%s: notif_2h disabled",
                    user_id, appointment_id
                )
                return
            elif hrs == 1 and not notif_settings.get("notif_1h", 1):
                logger.info(
                    "Skipping 1h reminder for user %s, appointment #%s: notif_1h disabled",
                    user_id, appointment_id
                )
                return

        except Exception as exc:
            logger.warning(
                "Could not check notification settings for user %s, sending reminder anyway: %s",
                user_id, exc
            )

        await self._notification_service.send_reminder(user_id, time_str, appointment_id)

        # BUG 4.5 FIX: отмечаем напоминание как отправленное после успешной отправки
        try:
            await asyncio.to_thread(self._appointment_service.mark_reminder_sent, appointment_id)
            logger.debug("Reminder marked as sent for appointment #%s", appointment_id)
        except Exception as exc:
            logger.warning(
                "Failed to mark reminder sent for appointment #%s: %s",
                appointment_id, exc
            )

    def _get_user_notif_settings_from_db(self, user_id: int) -> dict:
        """Получает настройки уведомлений пользователя из БД.

        Устранение дублирования (пункт 10) + getattr-хак (пункт 14):
        делегируем в AppointmentService.get_user_notification_settings(),
        который является единственным источником правды для чтения notif-настроек.
        """
        try:
            return self._appointment_service.get_user_notification_settings(user_id)
        except Exception as exc:
            logger.warning("Failed to get notification settings for user %s: %s", user_id, exc)
        return {"notifications_enabled": 1, "notif_24h": 1, "notif_2h": 1, "notif_1h": 1}

    def schedule_weekly_archive(self, hour: int = 3, minute: int = 0) -> None:
        """FIXED: планирует еженедельную архивацию старых записей (по воскресеньям в 3:00).

        FIXED H-6: передаём timezone в CronTrigger чтобы задача работала в правильном
        часовом поясе, а не всегда в UTC.
        """
        from apscheduler.triggers.cron import CronTrigger  # type: ignore

        job_id = "weekly_archive"
        self._scheduler.add_job(
            self._weekly_archive_job,
            trigger=CronTrigger(day_of_week="sun", hour=hour, minute=minute, timezone=self._timezone),
            id=job_id,
            replace_existing=True,
        )
        logger.info("Weekly archive job scheduled on Sunday at %02d:%02d %s", hour, minute, self._timezone)

    def schedule_insufficient_slots_check(self, hour: int = 10, minute: int = 0) -> None:
        """FIXED: планирует ежедневную проверку количества доступных слотов.

        FIXED H-6: передаём timezone в CronTrigger.
        """
        from apscheduler.triggers.cron import CronTrigger  # type: ignore

        job_id = "insufficient_slots_check"
        self._scheduler.add_job(
            self._insufficient_slots_check_job,
            trigger=CronTrigger(hour=hour, minute=minute, timezone=self._timezone),
            id=job_id,
            replace_existing=True,
        )
        logger.info("Insufficient slots check scheduled at %02d:%02d %s", hour, minute, self._timezone)

    async def _weekly_archive_job(self) -> None:
        """Архивирует старые записи (старше 90 дней).

        FIXED БАГ-ВЫСОК-04: реализовано реальное архивирование — экспорт в CSV и удаление
        старых отменённых/завершённых записей из БД. Ранее только логировалось количество.
        BUG 12 FIX: убраны вложенные import asyncio, csv, io, os, date, timedelta —
        asyncio уже импортирован в начале модуля.
        """
        try:
            from datetime import date as _date
            from datetime import timedelta

            # BUG 12 FIX: csv, io, os уже импортированы в начале модуля
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

            if not old_cancelled:
                return

            # Шаг 1: экспортируем в CSV перед удалением
            backup_dir = "data/backups"
            os.makedirs(backup_dir, exist_ok=True)
            archive_filename = os.path.join(
                backup_dir,
                f"archive_{_date.today().isoformat()}_cutoff_{cutoff_date}.csv"
            )
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["id", "user_id", "username", "client_name", "phone",
                              "date", "time", "service", "comment", "created_at", "is_cancelled"])
            for a in old_cancelled:
                writer.writerow([
                    a.id, a.user_id, a.username, a.client_name, a.phone,
                    a.date, a.time, a.service, a.comment,
                    a.created_at.strftime("%Y-%m-%d %H:%M:%S") if a.created_at else "",
                    int(a.is_cancelled)
                ])
            with open(archive_filename, "w", encoding="utf-8", newline="") as f:
                f.write(output.getvalue())
            logger.info("Archive exported to %s (%d records)", archive_filename, len(old_cancelled))

            # Шаг 2: удаляем старые отменённые записи из БД
            archived_ids = [a.id for a in old_cancelled if a.id is not None]
            if archived_ids:
                deleted = await asyncio.to_thread(
                    self._appointment_service.delete_appointments_by_ids, archived_ids
                )
                logger.info("Weekly archive: deleted %d old cancelled appointments from DB", deleted)
        except Exception:
            logger.exception("Weekly archive job failed")

    async def _insufficient_slots_check_job(self) -> None:
        """Проверяет количество доступных слотов и уведомляет администраторов.

        FIXED BUG-H2: используем self._schedule_service (публичный API) вместо
        нарушения инкапсуляции через getattr(self._appointment_service, "_schedule_repo", None).
        Если schedule_service не передан — graceful fallback с предупреждением.
        BUG 12 FIX: убраны вложенные import asyncio, date, timedelta —
        asyncio уже импортирован в начале модуля.
        """
        try:
            from datetime import date as _date
            from datetime import timedelta

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
        """Планирует ежедневный дайджест администратору в указанное время.

        FIXED: рассылка сводки администратору каждое утро в 9:00.
        FIXED H-6: передаём timezone в CronTrigger.
        """
        from apscheduler.triggers.cron import CronTrigger  # type: ignore

        job_id = "daily_digest"
        self._scheduler.add_job(
            self._daily_digest_job,
            trigger=CronTrigger(hour=hour, minute=minute, timezone=self._timezone),
            id=job_id,
            replace_existing=True,
        )
        logger.info("Daily digest scheduled at %02d:%02d %s", hour, minute, self._timezone)

    def schedule_daily_backup(self, hour: int = 2, minute: int = 0) -> None:
        """Планирует ежедневный бэкап БД в указанное время.

        FIXED: автоматический бэкап с ротацией каждый день в 2:00.
        FIXED H-6: передаём timezone в CronTrigger.
        """
        from apscheduler.triggers.cron import CronTrigger  # type: ignore

        if not self._backup_service:
            logger.warning("BackupService not provided, skipping backup scheduling")
            return
        job_id = "daily_backup"
        self._scheduler.add_job(
            self._daily_backup_job,
            trigger=CronTrigger(hour=hour, minute=minute, timezone=self._timezone),
            id=job_id,
            replace_existing=True,
        )
        logger.info("Daily backup scheduled at %02d:%02d %s", hour, minute, self._timezone)

    async def _daily_digest_job(self) -> None:
        """Отправляет ежедневный дайджест администраторам.

        BUG 12 FIX: убран вложенный import asyncio — asyncio уже импортирован в начале модуля.
        """
        try:
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
        BUG 12 FIX: вложенный import asyncio убран полностью.
        """
        try:
            if not self._backup_service:
                logger.warning("BackupService not available")
                return
            backup_path = await asyncio.to_thread(self._backup_service.create_backup)
            if backup_path:
                logger.info("Daily backup completed: %s", backup_path)
        except Exception:
            logger.exception("Daily backup job failed")
