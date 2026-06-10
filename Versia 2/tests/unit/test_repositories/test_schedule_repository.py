"""
tests/unit/test_repositories/test_schedule_repository.py
Unit-тесты для ScheduleRepository с реальной in-memory БД.
"""
from __future__ import annotations

import os
import tempfile

import pytest

from src.infrastructure.database.connection import DatabaseManager
from src.infrastructure.repositories.schedule_repository import ScheduleRepository


@pytest.fixture
def db_manager() -> DatabaseManager:
    """Создаёт временную БД для тестов."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    dm = DatabaseManager(db_path)
    dm.initialize_schema()
    yield dm
    DatabaseManager.reset()
    try:
        os.unlink(db_path)
        wal = db_path + "-wal"
        shm = db_path + "-shm"
        for p in [wal, shm]:
            if os.path.exists(p):
                os.unlink(p)
    except OSError:
        pass


@pytest.fixture
def repo(db_manager: DatabaseManager) -> ScheduleRepository:
    return ScheduleRepository(db_manager)


class TestAddWorkingDay:
    def test_add_new_day(self, repo: ScheduleRepository) -> None:
        result = repo.add_working_day("2030-01-15", ["09:00", "10:00", "11:00"])
        assert result is True

    def test_add_duplicate_day(self, repo: ScheduleRepository) -> None:
        repo.add_working_day("2030-01-15", ["09:00"])
        result = repo.add_working_day("2030-01-15", ["10:00"])
        assert result is False

    def test_add_day_creates_slots(self, repo: ScheduleRepository) -> None:
        repo.add_working_day("2030-01-15", ["09:00", "10:00"])
        slots = repo.get_free_slots("2030-01-15")
        assert len(slots) == 2
        times = [s.time for s in slots]
        assert "09:00" in times
        assert "10:00" in times


class TestBookSlot:
    def test_book_available_slot(self, repo: ScheduleRepository) -> None:
        repo.add_working_day("2030-01-15", ["09:00", "10:00"])
        result = repo.book_slot("2030-01-15", "09:00")
        assert result is True

    def test_book_already_booked_slot(self, repo: ScheduleRepository) -> None:
        repo.add_working_day("2030-01-15", ["09:00"])
        repo.book_slot("2030-01-15", "09:00")
        result = repo.book_slot("2030-01-15", "09:00")
        assert result is False

    def test_book_nonexistent_slot(self, repo: ScheduleRepository) -> None:
        result = repo.book_slot("2030-01-15", "09:00")
        assert result is False


class TestReleaseSlot:
    def test_release_booked_slot(self, repo: ScheduleRepository) -> None:
        repo.add_working_day("2030-01-15", ["09:00"])
        repo.book_slot("2030-01-15", "09:00")
        notifications = repo.release_slot("2030-01-15", "09:00")
        assert isinstance(notifications, list)
        slots = repo.get_free_slots("2030-01-15")
        assert len(slots) == 1

    def test_release_nonexistent_slot(self, repo: ScheduleRepository) -> None:
        result = repo.release_slot("2030-01-15", "09:00")
        assert result == []


class TestGetAvailableDates:
    def test_returns_dates_with_free_slots(self, repo: ScheduleRepository) -> None:
        repo.add_working_day("2030-01-15", ["09:00"])
        repo.add_working_day("2030-01-16", ["10:00"])
        result = repo.get_available_dates_in_range("2030-01-15", "2030-01-16")
        assert "2030-01-15" in result
        assert "2030-01-16" in result

    def test_excludes_fully_booked_dates(self, repo: ScheduleRepository) -> None:
        repo.add_working_day("2030-01-15", ["09:00"])
        repo.book_slot("2030-01-15", "09:00")
        result = repo.get_available_dates_in_range("2030-01-15", "2030-01-15")
        assert "2030-01-15" not in result


class TestDeleteWorkingDay:
    def test_delete_existing_day(self, repo: ScheduleRepository) -> None:
        repo.add_working_day("2030-01-15", ["09:00"])
        repo.delete_working_day("2030-01-15")
        day = repo.get_working_day("2030-01-15")
        assert day is None

    def test_delete_cascades_slots(self, repo: ScheduleRepository) -> None:
        repo.add_working_day("2030-01-15", ["09:00", "10:00"])
        repo.delete_working_day("2030-01-15")
        slots = repo.get_free_slots("2030-01-15")
        assert len(slots) == 0


class TestWaitlist:
    def test_join_waitlist(self, repo: ScheduleRepository) -> None:
        repo.add_working_day("2030-01-15", ["09:00"])
        result = repo.join_waitlist(user_id=123, date="2030-01-15")
        assert result is True

    def test_join_waitlist_duplicate(self, repo: ScheduleRepository) -> None:
        repo.add_working_day("2030-01-15", ["09:00"])
        repo.join_waitlist(user_id=123, date="2030-01-15")
        result = repo.join_waitlist(user_id=123, date="2030-01-15")
        assert result is False

    def test_release_notifies_waitlist(self, repo: ScheduleRepository) -> None:
        repo.add_working_day("2030-01-15", ["09:00"])
        repo.join_waitlist(user_id=999, date="2030-01-15")
        repo.book_slot("2030-01-15", "09:00")
        notifications = repo.release_slot("2030-01-15", "09:00")
        assert len(notifications) >= 1
        user_ids = [n[0] for n in notifications]
        assert 999 in user_ids


class TestWorkdayTemplates:
    def test_save_and_get_template(self, repo: ScheduleRepository) -> None:
        import json
        slots = json.dumps(["09:00", "10:00"])
        repo.save_workday_template("Стандарт", slots)
        templates = repo.get_workday_templates()
        assert len(templates) >= 1
        names = [t["name"] for t in templates]
        assert "Стандарт" in names

    def test_delete_template(self, repo: ScheduleRepository) -> None:
        import json
        slots = json.dumps(["09:00"])
        template_id = repo.save_workday_template("Временный", slots)
        repo.delete_workday_template(template_id)
        template = repo.get_workday_template(template_id)
        assert template is None
