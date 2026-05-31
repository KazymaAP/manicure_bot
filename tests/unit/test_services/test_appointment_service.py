"""
tests/unit/test_services/test_appointment_service.py
Unit-тесты для AppointmentService.
"""
from unittest.mock import MagicMock

import pytest

from src.application.dto.booking_dto import CreateBookingDTO
from src.application.services.appointment_service import AppointmentService
from src.domain.enums.appointment_status import AppointmentStatus
from src.domain.exceptions.appointment import (
    AppointmentAlreadyExistsError,
    MaxAppointmentsReachedError,
    SlotAlreadyBookedError,
)
from src.domain.models.appointment import Appointment
from src.infrastructure.database.connection import DatabaseManager


@pytest.fixture(autouse=True)
def reset_db_singleton():
    """FIXED BUG-C2: автоматически сбрасывает Singleton DatabaseManager между тестами.

    Без этого Singleton остаётся живым после первого теста с реальной БД,
    что вызывает RuntimeError при попытке переинициализации с другим db_path.
    autouse=True гарантирует выполнение для каждого теста в модуле.
    """
    # Сбрасываем перед тестом (на случай если предыдущий тест оставил состояние)
    DatabaseManager.reset()
    yield
    # Сбрасываем после теста (очистка после возможного интеграционного теста с реальной БД)
    DatabaseManager.reset()


@pytest.fixture
def mock_appointment_repo():
    repo = MagicMock()
    repo.count_active_by_user_id.return_value = 0
    repo.create.return_value = 1
    return repo


@pytest.fixture
def mock_schedule_repo():
    repo = MagicMock()
    repo.book_slot.return_value = True
    return repo


@pytest.fixture
def service(mock_appointment_repo, mock_schedule_repo):
    return AppointmentService(
        appointment_repo=mock_appointment_repo,
        schedule_repo=mock_schedule_repo,
        max_per_user=1,
    )


def make_dto(**kwargs):
    defaults = dict(
        user_id=123,
        client_name="Тест",
        phone="+79991234567",
        date="2026-12-01",
        time="10:00",
    )
    defaults.update(kwargs)
    return CreateBookingDTO(**defaults)


class TestCreateBooking:
    def test_create_booking_success(self, service, mock_appointment_repo, mock_schedule_repo):
        """Успешное создание записи."""
        dto = make_dto()
        result = service.create_booking(dto)
        assert result.appointment_id == 1
        assert result.client_name == "Тест"
        mock_schedule_repo.book_slot.assert_called_once_with("2026-12-01", "10:00")
        mock_appointment_repo.create.assert_called_once()

    def test_create_booking_slot_already_booked(self, service, mock_schedule_repo):
        """Слот занят — выбрасывает SlotAlreadyBookedError."""
        mock_schedule_repo.book_slot.return_value = False
        with pytest.raises(SlotAlreadyBookedError):
            service.create_booking(make_dto())

    def test_create_booking_max_appointments_reached(self, service, mock_appointment_repo):
        """Превышен лимит записей — выбрасывает MaxAppointmentsReachedError."""
        mock_appointment_repo.count_active_by_user_id.return_value = 1
        with pytest.raises(MaxAppointmentsReachedError):
            service.create_booking(make_dto())


class TestCancelAppointment:
    def _make_appointment(self, **kwargs):
        defaults = dict(
            id=1, user_id=123, client_name="Тест", phone="+7999",
            date="2026-12-01", time="10:00",
            status=AppointmentStatus.ACTIVE,
        )
        defaults.update(kwargs)
        return Appointment(**defaults)

    def test_cancel_by_user_success(self, service, mock_appointment_repo, mock_schedule_repo):
        """Клиент успешно отменяет свою запись."""
        appt = self._make_appointment()
        mock_appointment_repo.get_active_by_user_id.return_value = appt
        result = service.cancel_by_user(123)
        assert result is not None
        mock_appointment_repo.cancel.assert_called_once_with(1)
        mock_schedule_repo.release_slot.assert_called_once_with("2026-12-01", "10:00")

    def test_cancel_by_user_no_appointment(self, service, mock_appointment_repo):
        """Нет активной записи — возвращает None."""
        mock_appointment_repo.get_active_by_user_id.return_value = None
        result = service.cancel_by_user(123)
        assert result is None


class TestGetStatistics:
    def test_get_statistics_empty(self, service, mock_appointment_repo):
        """Статистика при пустой БД."""
        mock_appointment_repo.get_statistics_raw.return_value = {
            "total": 0,
            "confirmed": 0,
            "cancelled": 0,
            "today": 0,
            "week": 0,
        }
        stats = service.get_statistics()
        assert stats["total"] == 0
        assert stats["confirmed"] == 0
        assert stats["cancelled"] == 0
        mock_appointment_repo.get_statistics_raw.assert_called_once()
