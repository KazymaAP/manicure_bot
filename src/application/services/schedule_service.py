"""
src/application/services/schedule_service.py — Сервис расписания.

✅ Из v2_tar: get_available_dates, is_working_day, get_free_slots
✅ Улучшения v4: validate_time_format, get_available_dates возвращает set[str]
"""
from __future__ import annotations

import logging
import re
from datetime import date as _date
from datetime import timedelta

from src.application.dto.booking_dto import AddSlotDTO, AddWorkingDayDTO
from src.domain.exceptions import (
    PastDateError,
    WorkingDayAlreadyExistsError,
    WorkingDayNotFoundError,
)
from src.domain.models.time_slot import TimeSlot
from src.domain.models.working_day import WorkingDay
from src.infrastructure.repositories.schedule_repository import ScheduleRepository

logger = logging.getLogger(__name__)

_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


class ScheduleService:
    """Сервис управления расписанием мастера.

    Инкапсулирует бизнес-логику работы с рабочими днями и слотами.
    """

    def __init__(
        self,
        schedule_repo: ScheduleRepository,
        days_ahead: int = 30,
        default_time_slots: list[str] | None = None,
    ) -> None:
        """Инициализирует сервис.

        Args:
            schedule_repo: Репозиторий расписания.
            days_ahead: Горизонт расписания (дней вперёд). Берётся из settings.
            default_time_slots: Временные слоты по умолчанию.
        """
        self._schedule_repo = schedule_repo
        self._days_ahead = days_ahead
        self._default_time_slots = default_time_slots or []

    def add_working_day(self, dto: AddWorkingDayDTO) -> None:
        """Добавляет рабочий день.

        Args:
            dto: DTO с датой и временными слотами по умолчанию.

        Raises:
            PastDateError: Если дата в прошлом.
            ValueError: Если формат даты некорректен.
            WorkingDayAlreadyExistsError: Если день уже существует.
        """
        try:
            d = _date.fromisoformat(dto.date)
        except ValueError:
            raise ValueError(f"Invalid date format: {dto.date!r}, expected YYYY-MM-DD")

        if d < _date.today():
            raise PastDateError(dto.date)

        success = self._schedule_repo.add_working_day(
            dto.date, list(dto.default_slots)
        )
        if not success:
            raise WorkingDayAlreadyExistsError(dto.date)

        logger.info("Working day added: %s", dto.date)

    def get_available_dates(self, from_date: _date, days_ahead: int) -> set[str]:
        """Возвращает множество доступных дат для записи (оптимизировано N+1).

        Фильтрует дни с хотя бы одним свободным слотом.

        Args:
            from_date: Начальная дата.
            days_ahead: Количество дней вперёд.

        Returns:
            Множество строк дат «YYYY-MM-DD».
        """
        to_date = from_date + timedelta(days=days_ahead)
        return self._schedule_repo.get_available_dates_in_range(
            from_date.isoformat(), to_date.isoformat()
        )

    def get_all_working_days(self, from_date: _date, days_ahead: int) -> list[WorkingDay]:
        """Возвращает все рабочие дни в диапазоне (включая закрытые).

        Args:
            from_date: Начальная дата.
            days_ahead: Количество дней вперёд.

        Returns:
            Список рабочих дней.
        """
        to_date = from_date + timedelta(days=days_ahead)
        return self._schedule_repo.get_all_days_in_range(
            from_date.isoformat(), to_date.isoformat()
        )

    def is_working_day(self, date_str: str) -> bool:
        """Проверяет, является ли дата открытым рабочим днём.

        Args:
            date_str: Дата «YYYY-MM-DD».

        Returns:
            True если день открыт.
        """
        return self._schedule_repo.is_working_day(date_str)

    def get_free_slots(self, date_str: str) -> list[TimeSlot]:
        """Возвращает свободные слоты для даты.

        Args:
            date_str: Дата «YYYY-MM-DD».

        Returns:
            Список свободных слотов.
        """
        return self._schedule_repo.get_free_slots(date_str)

    def get_all_slots(self, date_str: str) -> list[TimeSlot]:
        """Возвращает все слоты для даты (включая забронированные).

        Args:
            date_str: Дата «YYYY-MM-DD».

        Returns:
            Список всех слотов.
        """
        return self._schedule_repo.get_all_slots(date_str)

    def toggle_day_status(self, date_str: str, is_closed: bool) -> None:
        """Открывает/закрывает рабочий день.

        Args:
            date_str: Дата «YYYY-MM-DD».
            is_closed: True для закрытия, False для открытия.

        Raises:
            WorkingDayNotFoundError: Если день не существует.
        """
        day = self._schedule_repo.get_working_day(date_str)
        if not day:
            raise WorkingDayNotFoundError(date_str)
        self._schedule_repo.set_day_status(date_str, is_closed)
        logger.info("Day %s status set to closed=%s", date_str, is_closed)

    def open_day(self, date_str: str) -> None:
        """Открывает рабочий день, создав его с дефолтными слотами если нужно.

        Args:
            date_str: Дата «YYYY-MM-DD».
        """
        day = self._schedule_repo.get_working_day(date_str)
        if not day:
            self._schedule_repo.add_working_day(date_str, self._default_time_slots)
        self._schedule_repo.set_day_status(date_str, is_closed=False)
        logger.info("Day %s opened", date_str)

    def close_day(self, date_str: str) -> None:
        """Закрывает рабочий день.

        Args:
            date_str: Дата «YYYY-MM-DD».
        """
        day = self._schedule_repo.get_working_day(date_str)
        if not day:
            self._schedule_repo.add_working_day(date_str, self._default_time_slots)
        self._schedule_repo.set_day_status(date_str, is_closed=True)
        logger.info("Day %s closed", date_str)

    def ensure_working_day_exists(self, date_str: str) -> None:
        """Гарантирует, что рабочий день существует (с дефолтными слотами если нужно).

        Args:
            date_str: Дата «YYYY-MM-DD».
        """
        day = self._schedule_repo.get_working_day(date_str)
        if not day:
            self._schedule_repo.add_working_day(date_str, self._default_time_slots)
            logger.debug("Working day %s created with default slots", date_str)

    def add_slot_from_dto(self, dto: AddSlotDTO) -> bool:
        """Добавляет временной слот из DTO.

        Args:
            dto: DTO с датой и временем слота.

        Returns:
            True если слот добавлен; False если уже существует.

        Raises:
            ValueError: Если формат времени некорректен.
        """
        if not _TIME_RE.match(dto.time):
            raise ValueError(f"Invalid time format: {dto.time!r}, expected HH:MM")
        h, m = map(int, dto.time.split(":"))
        if not (0 <= h < 24 and 0 <= m < 60):
            raise ValueError(f"Time out of range: {dto.time!r}")

        return self._schedule_repo.add_time_slot(dto.date, dto.time)

    def delete_slot(self, date_str: str, time_str: str) -> bool:
        """Удаляет свободный временной слот.

        Args:
            date_str: Дата «YYYY-MM-DD».
            time_str: Время «HH:MM».

        Returns:
            True если слот удалён.
        """
        return self._schedule_repo.delete_time_slot(date_str, time_str)

     # ── Алиасы и удобные методы для хэндлеров ────────────────────────────

    async def get_available_dates_async(self) -> list[str]:
        """Async-обёртка: возвращает список доступных дат.
        
        FIXED: обвёрнут синхронный SQL-запрос в asyncio.to_thread чтобы не блокировать event loop.
        """
        import asyncio
        result = await asyncio.to_thread(
            self.get_available_dates,
            from_date=_date.today(),
            days_ahead=self._days_ahead
        )
        return sorted(result)

    async def get_available_slots(self, date_str: str) -> list[TimeSlot]:
        """Async-обёртка для get_free_slots.
        
        FIXED: обвёрнут синхронный SQL-запрос в asyncio.to_thread чтобы не блокировать event loop.
        """
        import asyncio
        return await asyncio.to_thread(self._schedule_repo.get_free_slots, date_str)

    def get_workday_templates(self) -> list[dict]:
        """Возвращает все сохранённые шаблоны рабочих дней."""
        return self._schedule_repo.get_workday_templates()

    def save_workday_template(self, name: str, schedule: str) -> int:
        """Сохраняет шаблон рабочих дней."""
        return self._schedule_repo.save_workday_template(name, schedule)

    def get_nearest_free_slots(self, limit: int = 5) -> list[tuple[str, str]]:
        """Возвращает ближайшие свободные слоты (date, time) в пределах horizon."""
        from datetime import date as _date, timedelta

        result: list[tuple[str, str]] = []
        today = _date.today()
        for day_offset in range(0, self._days_ahead + 1):
            d = today + timedelta(days=day_offset)
            date_str = d.isoformat()
            slots = self._schedule_repo.get_free_slots(date_str)
            for s in slots:
                result.append((date_str, s.time))
                if len(result) >= limit:
                    return result
        return result

    async def get_nearest_slots_async(self, limit: int = 5) -> list[tuple[str, str]]:
        """Async-обёртка для get_nearest_free_slots."""
        return self.get_nearest_free_slots(limit=limit)

    async def join_waitlist(self, user_id: int, date: str) -> bool:
        """Добавляет пользователя в лист ожидания (асинхронная оболочка)."""
        return self._schedule_repo.join_waitlist(user_id, date)

    # FIXED: добавлен метод для вывода ближайших свободных слотов без открытия календаря и поддержка waitlist.
    async def get_all_working_dates(self) -> list[str]:
        """Async-обёртка: возвращает все рабочие даты в горизонте настроек (days_ahead)."""
        days = self._schedule_repo.get_all_days_in_range(
            _date.today().isoformat(),
            (_date.today() + timedelta(days=self._days_ahead)).isoformat(),
        )
        return [d.date for d in days]

    async def get_slots_for_date(self, date_str: str) -> list[TimeSlot]:
        """Async-обёртка для get_all_slots."""
        return self._schedule_repo.get_all_slots(date_str)

    async def add_slot(self, date_str: str, time_str: str) -> bool:
        """Async-обёртка для добавления слота (принимает строки напрямую)."""
        if not _TIME_RE.match(time_str):
            raise ValueError(f"Invalid time format: {time_str!r}, expected HH:MM")
        h, m = map(int, time_str.split(":"))
        if not (0 <= h < 24 and 0 <= m < 60):
            raise ValueError(f"Time out of range: {time_str!r}")
        return self._schedule_repo.add_time_slot(date_str, time_str)

    async def remove_slot(self, date_str: str, time_str: str) -> bool:
        """Async-обёртка для delete_slot."""
        return self._schedule_repo.delete_time_slot(date_str, time_str)

    async def toggle_working_day(self, date_str: str) -> bool:
        """Переключает статус дня. Возвращает True если день теперь открыт."""
        day = self._schedule_repo.get_working_day(date_str)
        if not day:
            # Создаём день, если не существует
            self._schedule_repo.add_working_day(date_str, [])
            self._schedule_repo.set_day_status(date_str, is_closed=False)
            return True
        new_status = not day.is_open
        self._schedule_repo.set_day_status(date_str, is_closed=not new_status)
        return new_status
