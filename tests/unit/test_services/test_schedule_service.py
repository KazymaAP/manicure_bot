"""
tests/unit/test_services/test_schedule_service.py
Unit-тесты для ScheduleService.
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from src.application.dto.booking_dto import AddWorkingDayDTO
from src.application.services.schedule_service import ScheduleService
from src.domain.exceptions.schedule import PastDateError, WorkingDayAlreadyExistsError
from src.domain.models.time_slot import TimeSlot
from src.domain.models.working_day import WorkingDay
from src.domain.enums.day_status import DayStatus


@pytest.fixture
def mock_schedule_repo():
    repo = MagicMock()
    repo.add_working_day.return_value = True
    repo.get_available_dates_in_range.return_value = set()
    return repo


@pytest.fixture
def service(mock_schedule_repo):
    return ScheduleService(
        schedule_repo=mock_schedule_repo,
        days_ahead=30,
        default_time_slots=["09:00", "10:00", "11:00"],
    )


class TestAddWorkingDay:
    def test_add_working_day_success(self, service, mock_schedule_repo):
        """Добавление рабочего дня в будущем — успешно."""
        future_date = (date.today() + timedelta(days=5)).isoformat()
        dto = AddWorkingDayDTO(date=future_date, default_slots=("09:00", "10:00"))
        service.add_working_day(dto)
        mock_schedule_repo.add_working_day.assert_called_once_with(future_date, ["09:00", "10:00"])

    def test_add_working_day_past_raises(self, service):
        """Добавление дня в прошлом — выбрасывает PastDateError."""
        past_date = (date.today() - timedelta(days=1)).isoformat()
        dto = AddWorkingDayDTO(date=past_date)
        with pytest.raises(PastDateError):
            service.add_working_day(dto)

    def test_add_working_day_already_exists(self, service, mock_schedule_repo):
        """День уже существует — выбрасывает WorkingDayAlreadyExistsError."""
        mock_schedule_repo.add_working_day.return_value = False
        future_date = (date.today() + timedelta(days=5)).isoformat()
        dto = AddWorkingDayDTO(date=future_date)
        with pytest.raises(WorkingDayAlreadyExistsError):
            service.add_working_day(dto)

    def test_add_working_day_invalid_date_format(self, service):
        """Некорректный формат даты — выбрасывает ValueError."""
        dto = AddWorkingDayDTO(date="not-a-date")
        with pytest.raises(ValueError):
            service.add_working_day(dto)


class TestGetAvailableDates:
    def test_returns_available_dates(self, service, mock_schedule_repo):
        """get_available_dates возвращает множество доступных дат."""
        today = date.today()
        expected = {"2026-12-01", "2026-12-02"}
        mock_schedule_repo.get_available_dates_in_range.return_value = expected
        result = service.get_available_dates(today, 30)
        assert result == expected

    def test_empty_schedule_returns_empty_set(self, service, mock_schedule_repo):
        """Пустое расписание возвращает пустое множество."""
        mock_schedule_repo.get_available_dates_in_range.return_value = set()
        result = service.get_available_dates(date.today(), 30)
        assert result == set()
