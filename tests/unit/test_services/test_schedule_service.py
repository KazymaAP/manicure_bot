"""
tests/unit/test_services/test_schedule_service.py
Unit-тесты для ScheduleService.
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from src.application.dto.booking_dto import AddSlotDTO, AddWorkingDayDTO
from src.application.services.schedule_service import ScheduleService
from src.domain.exceptions.schedule import (
    PastDateError,
    WorkingDayAlreadyExistsError,
    WorkingDayNotFoundError,
)
from src.domain.models.time_slot import TimeSlot
from src.domain.models.working_day import WorkingDay


@pytest.fixture
def mock_schedule_repo() -> MagicMock:
    repo = MagicMock()
    repo.add_working_day.return_value = True
    repo.get_available_dates_in_range.return_value = set()
    repo.get_free_slots.return_value = []
    repo.is_working_day.return_value = True
    return repo


@pytest.fixture
def service(mock_schedule_repo: MagicMock) -> ScheduleService:
    return ScheduleService(
        schedule_repo=mock_schedule_repo,
        days_ahead=30,
        default_time_slots=["09:00", "10:00", "11:00"],
    )


# ── Добавление рабочего дня ───────────────────────────────────────────────────

class TestAddWorkingDay:
    def test_success(self, service: ScheduleService, mock_schedule_repo: MagicMock) -> None:
        """Добавление рабочего дня в будущем."""
        future_date = (date.today() + timedelta(days=5)).isoformat()
        dto = AddWorkingDayDTO(date=future_date, default_slots=("09:00", "10:00"))
        service.add_working_day(dto)
        mock_schedule_repo.add_working_day.assert_called_once_with(future_date, ["09:00", "10:00"])

    def test_past_date_raises(self, service: ScheduleService) -> None:
        """Дата в прошлом → PastDateError."""
        past_date = (date.today() - timedelta(days=1)).isoformat()
        dto = AddWorkingDayDTO(date=past_date)
        with pytest.raises(PastDateError) as exc_info:
            service.add_working_day(dto)
        assert exc_info.value.date == past_date

    def test_already_exists_raises(
        self, service: ScheduleService, mock_schedule_repo: MagicMock
    ) -> None:
        """День уже существует → WorkingDayAlreadyExistsError."""
        mock_schedule_repo.add_working_day.return_value = False
        future_date = (date.today() + timedelta(days=5)).isoformat()
        dto = AddWorkingDayDTO(date=future_date)
        with pytest.raises(WorkingDayAlreadyExistsError):
            service.add_working_day(dto)

    def test_invalid_date_format_raises(self, service: ScheduleService) -> None:
        """Некорректный формат даты → ValueError."""
        dto = AddWorkingDayDTO(date="not-a-date")
        with pytest.raises(ValueError):
            service.add_working_day(dto)

    def test_today_allowed(self, service: ScheduleService, mock_schedule_repo: MagicMock) -> None:
        """Сегодняшняя дата разрешена (не считается прошлым)."""
        today = date.today().isoformat()
        dto = AddWorkingDayDTO(date=today)
        # Сегодня не прошлое (d < today() == False), поэтому исключение не должно подняться
        service.add_working_day(dto)
        mock_schedule_repo.add_working_day.assert_called_once()


# ── Получение доступных дат ───────────────────────────────────────────────────

class TestGetAvailableDates:
    def test_returns_available_dates(
        self, service: ScheduleService, mock_schedule_repo: MagicMock
    ) -> None:
        expected = {"2026-12-01", "2026-12-02"}
        mock_schedule_repo.get_available_dates_in_range.return_value = expected
        result = service.get_available_dates(date.today(), 30)
        assert result == expected

    def test_empty_schedule(
        self, service: ScheduleService, mock_schedule_repo: MagicMock
    ) -> None:
        mock_schedule_repo.get_available_dates_in_range.return_value = set()
        result = service.get_available_dates(date.today(), 30)
        assert result == set()

    def test_range_calculation(
        self, service: ScheduleService, mock_schedule_repo: MagicMock
    ) -> None:
        """Проверяем что диапазон передаётся корректно."""
        today = date.today()
        days = 14
        mock_schedule_repo.get_available_dates_in_range.return_value = set()
        service.get_available_dates(today, days)
        expected_to = (today + timedelta(days=days)).isoformat()
        mock_schedule_repo.get_available_dates_in_range.assert_called_once_with(
            today.isoformat(), expected_to
        )


# ── Добавление слота ──────────────────────────────────────────────────────────

class TestAddSlot:
    def test_add_slot_success(
        self, service: ScheduleService, mock_schedule_repo: MagicMock
    ) -> None:
        mock_schedule_repo.add_time_slot.return_value = True
        future_date = (date.today() + timedelta(days=1)).isoformat()
        result = service.add_slot_from_dto(AddSlotDTO(date=future_date, time="12:00"))
        assert result is True

    def test_invalid_time_format_raises(self, service: ScheduleService) -> None:
        with pytest.raises(ValueError, match="Invalid time format"):
            service.add_slot_from_dto(AddSlotDTO(date="2026-12-01", time="9:00"))

    def test_time_out_of_range_raises(self, service: ScheduleService) -> None:
        with pytest.raises(ValueError, match="out of range"):
            service.add_slot_from_dto(AddSlotDTO(date="2026-12-01", time="25:00"))

    def test_duplicate_slot(
        self, service: ScheduleService, mock_schedule_repo: MagicMock
    ) -> None:
        mock_schedule_repo.add_time_slot.return_value = False
        result = service.add_slot_from_dto(AddSlotDTO(date="2026-12-01", time="10:00"))
        assert result is False


# ── Управление статусом дня ───────────────────────────────────────────────────

class TestToggleDayStatus:
    def test_toggle_existing_day(
        self, service: ScheduleService, mock_schedule_repo: MagicMock
    ) -> None:
        mock_wd = MagicMock(spec=WorkingDay)
        mock_schedule_repo.get_working_day.return_value = mock_wd
        service.toggle_day_status("2026-12-01", is_closed=True)
        mock_schedule_repo.set_day_status.assert_called_once_with("2026-12-01", True)

    def test_toggle_nonexistent_day_raises(
        self, service: ScheduleService, mock_schedule_repo: MagicMock
    ) -> None:
        mock_schedule_repo.get_working_day.return_value = None
        with pytest.raises(WorkingDayNotFoundError):
            service.toggle_day_status("2026-12-01", is_closed=True)


# ── Шаблоны расписания ────────────────────────────────────────────────────────

class TestWorkdayTemplates:
    def test_get_templates(
        self, service: ScheduleService, mock_schedule_repo: MagicMock
    ) -> None:
        mock_schedule_repo.get_workday_templates.return_value = [
            {"id": 1, "name": "Полный день", "slots": '["09:00","10:00"]'},
        ]
        templates = service.get_workday_templates()
        assert len(templates) == 1
        assert templates[0]["name"] == "Полный день"

    def test_delete_template(
        self, service: ScheduleService, mock_schedule_repo: MagicMock
    ) -> None:
        service.delete_workday_template(1)
        mock_schedule_repo.delete_workday_template.assert_called_once_with(1)


# ── Async-методы ─────────────────────────────────────────────────────────────

class TestAsyncMethods:
    @pytest.mark.asyncio
    async def test_get_available_dates_async(
        self, service: ScheduleService, mock_schedule_repo: MagicMock
    ) -> None:
        mock_schedule_repo.get_available_dates_in_range.return_value = {
            "2026-12-02", "2026-12-01"
        }
        dates = await service.get_available_dates_async()
        assert dates == sorted(["2026-12-01", "2026-12-02"])

    @pytest.mark.asyncio
    async def test_get_available_slots(
        self, service: ScheduleService, mock_schedule_repo: MagicMock
    ) -> None:
        mock_slot = MagicMock(spec=TimeSlot)
        mock_slot.time = "10:00"
        mock_schedule_repo.get_free_slots.return_value = [mock_slot]
        slots = await service.get_available_slots("2026-12-01")
        assert len(slots) == 1
        assert slots[0].time == "10:00"
