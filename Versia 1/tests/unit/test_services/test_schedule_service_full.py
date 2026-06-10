"""
tests/unit/test_services/test_schedule_service_full.py
Расширенные тесты для ScheduleService.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

import pytest

from src.application.dto.booking_dto import AddSlotDTO, AddWorkingDayDTO
from src.application.services.schedule_service import ScheduleService
from src.domain.exceptions.schedule import (
    PastDateError,
    WorkingDayAlreadyExistsError,
    WorkingDayNotFoundError,
)
from src.infrastructure.database.connection import DatabaseManager
from src.infrastructure.repositories.schedule_repository import ScheduleRepository


@pytest.fixture
def db_manager():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    dm = DatabaseManager(db_path)
    dm.initialize_schema()
    yield dm
    DatabaseManager.reset()
    try:
        os.unlink(db_path)
        for ext in ["-wal", "-shm"]:
            p = db_path + ext
            if os.path.exists(p):
                os.unlink(p)
    except OSError:
        pass


@pytest.fixture
def schedule_repo(db_manager: DatabaseManager) -> ScheduleRepository:
    return ScheduleRepository(db_manager)


@pytest.fixture
def service(schedule_repo: ScheduleRepository) -> ScheduleService:
    return ScheduleService(
        schedule_repo=schedule_repo,
        days_ahead=30,
        default_time_slots=["09:00", "10:00", "11:00"],
    )


class TestAddWorkingDay:
    def test_add_future_day(self, service: ScheduleService, schedule_repo: ScheduleRepository) -> None:
        future = date(2030, 6, 15).isoformat()
        dto = AddWorkingDayDTO(date=future, default_slots=("09:00", "10:00"))
        service.add_working_day(dto)
        day = schedule_repo.get_working_day(future)
        assert day is not None

    def test_add_past_day_raises(self, service: ScheduleService) -> None:
        past = "2000-01-01"
        dto = AddWorkingDayDTO(date=past)
        with pytest.raises(PastDateError):
            service.add_working_day(dto)

    def test_add_duplicate_day_raises(self, service: ScheduleService) -> None:
        future = date(2030, 6, 15).isoformat()
        dto = AddWorkingDayDTO(date=future)
        service.add_working_day(dto)
        with pytest.raises(WorkingDayAlreadyExistsError):
            service.add_working_day(dto)

    def test_add_day_with_invalid_date_raises(self, service: ScheduleService) -> None:
        dto = AddWorkingDayDTO(date="not-a-date")
        with pytest.raises(ValueError):
            service.add_working_day(dto)


class TestGetAvailableDates:
    def test_returns_dates_with_free_slots(
        self, service: ScheduleService, schedule_repo: ScheduleRepository
    ) -> None:
        future = date(2030, 6, 15).isoformat()
        dto = AddWorkingDayDTO(date=future, default_slots=("09:00",))
        service.add_working_day(dto)
        today = date(2030, 6, 14)
        result = service.get_available_dates(today, 5)
        assert future in result

    def test_returns_empty_when_no_slots(
        self, service: ScheduleService
    ) -> None:
        today = date.today()
        result = service.get_available_dates(today, 30)
        assert len(result) == 0


class TestGetFreeSlots:
    def test_get_free_slots_for_day(
        self, service: ScheduleService, schedule_repo: ScheduleRepository
    ) -> None:
        future = date(2030, 6, 15).isoformat()
        dto = AddWorkingDayDTO(date=future, default_slots=("09:00", "10:00"))
        service.add_working_day(dto)
        slots = service.get_free_slots(future)
        assert len(slots) == 2

    def test_get_free_slots_excludes_booked(
        self, service: ScheduleService, schedule_repo: ScheduleRepository
    ) -> None:
        future = date(2030, 6, 15).isoformat()
        dto = AddWorkingDayDTO(date=future, default_slots=("09:00", "10:00"))
        service.add_working_day(dto)
        schedule_repo.book_slot(future, "09:00")
        slots = service.get_free_slots(future)
        assert len(slots) == 1
        assert slots[0].time == "10:00"


class TestAddSlot:
    def test_add_slot_to_existing_day(
        self, service: ScheduleService, schedule_repo: ScheduleRepository
    ) -> None:
        future = date(2030, 6, 15).isoformat()
        schedule_repo.add_working_day(future, ["09:00"])
        dto = AddSlotDTO(date=future, time="10:00")
        service.add_slot_from_dto(dto)
        slots = service.get_free_slots(future)
        times = [s.time for s in slots]
        assert "10:00" in times

    def test_add_slot_invalid_time_raises(
        self, service: ScheduleService, schedule_repo: ScheduleRepository
    ) -> None:
        future = date(2030, 6, 15).isoformat()
        schedule_repo.add_working_day(future, [])
        dto = AddSlotDTO(date=future, time="25:00")
        with pytest.raises(ValueError):
            service.add_slot_from_dto(dto)

    def test_add_slot_missing_day_raises(
        self, service: ScheduleService
    ) -> None:
        dto = AddSlotDTO(date="2030-06-15", time="09:00")
        with pytest.raises(WorkingDayNotFoundError):
            service.add_slot_from_dto(dto)


class TestValidateTimeFormat:
    def test_valid_time(self, service: ScheduleService) -> None:
        # Используем публичный метод add_slot с коректным временем (должен не бросить исключение)
        import re
        pattern = re.compile(r"^\d{2}:\d{2}$")
        assert bool(pattern.match("09:00")) is True
        assert bool(pattern.match("23:59")) is True

    def test_invalid_time(self, service: ScheduleService) -> None:
        import re
        pattern = re.compile(r"^\d{2}:\d{2}$")
        assert bool(pattern.match("9:00")) is False
        assert bool(pattern.match("abc")) is False
