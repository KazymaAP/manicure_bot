"""
tests/unit/test_repositories/test_appointment_repository.py
Unit-тесты для AppointmentRepository с реальной in-memory БД.
"""
from __future__ import annotations

import os
import tempfile

import pytest

from src.domain.models.appointment import Appointment
from src.infrastructure.database.connection import DatabaseManager
from src.infrastructure.repositories.appointment_repository import AppointmentRepository


@pytest.fixture
def db_manager() -> DatabaseManager:
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
def repo(db_manager: DatabaseManager) -> AppointmentRepository:
    return AppointmentRepository(db_manager)


def make_appointment(**kwargs) -> Appointment:
    defaults = {
        "id": None,
        "user_id": 123,
        "client_name": "Иванова Анна",
        "phone": "+79991234567",
        "date": "2030-06-15",
        "time": "10:00",
    }
    defaults.update(kwargs)
    return Appointment(**defaults)


class TestCreate:
    def test_create_returns_id(self, repo: AppointmentRepository) -> None:
        appt = make_appointment()
        appt_id = repo.create(appt)
        assert isinstance(appt_id, int)
        assert appt_id > 0

    def test_created_appointment_retrievable(self, repo: AppointmentRepository) -> None:
        appt = make_appointment()
        appt_id = repo.create(appt)
        retrieved = repo.get_by_id(appt_id)
        assert retrieved is not None
        assert retrieved.client_name == "Иванова Анна"
        assert retrieved.phone == "+79991234567"
        assert retrieved.date == "2030-06-15"
        assert retrieved.time == "10:00"


class TestGetByUserId:
    def test_get_active_by_user_id(self, repo: AppointmentRepository) -> None:
        appt = make_appointment()
        appt_id = repo.create(appt)
        result = repo.get_active_by_user_id(123)
        assert result is not None
        assert result.id == appt_id

    def test_get_active_by_user_id_not_found(self, repo: AppointmentRepository) -> None:
        result = repo.get_active_by_user_id(999)
        assert result is None

    def test_get_active_list_returns_multiple(self, repo: AppointmentRepository) -> None:
        repo.create(make_appointment(time="10:00"))
        repo.create(make_appointment(time="11:00"))
        results = repo.get_active_list_by_user_id(123)
        assert len(results) == 2

    def test_count_active(self, repo: AppointmentRepository) -> None:
        repo.create(make_appointment(time="10:00"))
        repo.create(make_appointment(time="11:00"))
        count = repo.count_active_by_user_id(123)
        assert count == 2


class TestCancel:
    def test_cancel_sets_is_cancelled(self, repo: AppointmentRepository) -> None:
        appt_id = repo.create(make_appointment())
        result = repo.cancel(appt_id)
        assert result is True
        retrieved = repo.get_by_id(appt_id)
        assert retrieved is not None
        assert retrieved.is_cancelled

    def test_cancel_already_cancelled_returns_false(self, repo: AppointmentRepository) -> None:
        appt_id = repo.create(make_appointment())
        repo.cancel(appt_id)
        result = repo.cancel(appt_id)
        assert result is False

    def test_cancelled_not_in_active_list(self, repo: AppointmentRepository) -> None:
        appt_id = repo.create(make_appointment())
        repo.cancel(appt_id)
        active = repo.get_active_by_user_id(123)
        assert active is None


class TestGetByDate:
    def test_get_by_date_returns_appointments(self, repo: AppointmentRepository) -> None:
        repo.create(make_appointment(date="2030-06-15", time="10:00"))
        repo.create(make_appointment(date="2030-06-15", time="11:00", user_id=456))
        result = repo.get_by_date("2030-06-15")
        assert len(result) == 2

    def test_get_by_date_excludes_cancelled(self, repo: AppointmentRepository) -> None:
        appt_id = repo.create(make_appointment(date="2030-06-15"))
        repo.cancel(appt_id)
        result = repo.get_by_date("2030-06-15")
        assert len(result) == 0


class TestSearch:
    def test_search_by_name(self, repo: AppointmentRepository) -> None:
        repo.create(make_appointment(client_name="Тестовый Клиент"))
        results = repo.search_by_client("Тестовый")
        assert len(results) >= 1
        assert results[0].client_name == "Тестовый Клиент"

    def test_search_by_phone(self, repo: AppointmentRepository) -> None:
        repo.create(make_appointment(phone="+70001112233"))
        results = repo.search_by_client("+70001112233")
        assert len(results) >= 1

    def test_search_escapes_percent(self, repo: AppointmentRepository) -> None:
        """LIKE-инъекция через % не должна возвращать все записи."""
        repo.create(make_appointment(client_name="Обычный Клиент"))
        results = repo.search_by_client("%")
        # Строка "%" должна экранироваться — результатов нет (клиент с именем % не существует)
        assert all(r.client_name != "%" for r in results)


class TestStatistics:
    def test_statistics_empty(self, repo: AppointmentRepository) -> None:
        stats = repo.get_statistics_raw()
        assert stats["total"] == 0
        assert stats["confirmed"] == 0
        assert stats["cancelled"] == 0

    def test_statistics_with_data(self, repo: AppointmentRepository) -> None:
        repo.create(make_appointment(time="10:00"))
        appt_id = repo.create(make_appointment(time="11:00", user_id=456))
        repo.cancel(appt_id)
        stats = repo.get_statistics_raw()
        assert stats["total"] == 2
        assert stats["confirmed"] == 1
        assert stats["cancelled"] == 1


class TestBlacklist:
    def test_block_and_check(self, repo: AppointmentRepository) -> None:
        repo.block_user(777, "Тест")
        assert repo.is_user_blocked(777) is True

    def test_unblock(self, repo: AppointmentRepository) -> None:
        repo.block_user(777, "Тест")
        repo.unblock_user(777)
        assert repo.is_user_blocked(777) is False

    def test_not_blocked_by_default(self, repo: AppointmentRepository) -> None:
        assert repo.is_user_blocked(999) is False


class TestDeleteByIds:
    def test_delete_by_ids(self, repo: AppointmentRepository) -> None:
        id1 = repo.create(make_appointment(time="10:00"))
        id2 = repo.create(make_appointment(time="11:00", user_id=456))
        deleted = repo.delete_by_ids([id1, id2])
        assert deleted == 2
        assert repo.get_by_id(id1) is None
        assert repo.get_by_id(id2) is None

    def test_delete_empty_list(self, repo: AppointmentRepository) -> None:
        deleted = repo.delete_by_ids([])
        assert deleted == 0


class TestMarkReminderSent:
    def test_mark_reminder_sent(self, repo: AppointmentRepository) -> None:
        appt_id = repo.create(make_appointment())
        repo.mark_reminder_sent(appt_id)
        appt = repo.get_by_id(appt_id)
        assert appt is not None
        assert appt.reminder_sent is True


class TestPagination:
    def test_get_all_active_paginated(self, repo: AppointmentRepository) -> None:
        times = ["09:00", "10:00", "11:00", "12:00", "13:00"]
        for i, t in enumerate(times):
            repo.create(make_appointment(time=t, user_id=100 + i))
        page1 = repo.get_all_active_paginated(limit=3, offset=0)
        page2 = repo.get_all_active_paginated(limit=3, offset=3)
        assert len(page1) == 3
        assert len(page2) == 2

    def test_count_all_active(self, repo: AppointmentRepository) -> None:
        times = ["09:00", "10:00", "11:00"]
        for i, t in enumerate(times):
            repo.create(make_appointment(time=t, user_id=100 + i))
        assert repo.count_all_active() == 3
