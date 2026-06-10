"""
tests/unit/test_services/test_appointment_service.py
Unit-тесты для AppointmentService.

Тестирует бизнес-логику без реальной БД (mock-репозитории).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.application.dto.booking_dto import BookingResultDTO, CreateBookingDTO
from src.application.services.appointment_service import AppointmentService
from src.domain.enums.appointment_status import AppointmentStatus
from src.domain.exceptions.appointment import (
    AppointmentAlreadyCancelledError,
    AppointmentNotFoundError,
    BlacklistedUserError,
    MaxAppointmentsReachedError,
    SlotAlreadyBookedError,
)
from src.domain.models.appointment import Appointment
from src.infrastructure.database.connection import DatabaseManager  # noqa: F401 — used in conftest

# ── Фикстуры ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_appointment_repo() -> MagicMock:
    repo = MagicMock()
    repo.count_active_by_user_id.return_value = 0
    repo.create.return_value = 1
    repo.is_user_blocked.return_value = False
    # Убираем _db чтобы AppointmentService использовал Path B (mock-путь)
    repo._db = None
    repo.db = None
    return repo


@pytest.fixture
def mock_schedule_repo() -> MagicMock:
    repo = MagicMock()
    repo.book_slot.return_value = True
    repo.release_slot.return_value = []
    return repo


@pytest.fixture
def service(mock_appointment_repo: MagicMock, mock_schedule_repo: MagicMock) -> AppointmentService:
    return AppointmentService(
        appointment_repo=mock_appointment_repo,
        schedule_repo=mock_schedule_repo,
        max_per_user=1,
    )


def make_dto(**kwargs) -> CreateBookingDTO:
    defaults = {
        "user_id": 123,
        "client_name": "Тест",
        "phone": "+79991234567",
        "date": "2026-12-01",
        "time": "10:00",
    }
    defaults.update(kwargs)
    return CreateBookingDTO(**defaults)


def make_appointment(**kwargs) -> Appointment:
    defaults = {
        "id": 1,
        "user_id": 123,
        "client_name": "Тест",
        "phone": "+79991234567",
        "date": "2026-12-01",
        "time": "10:00",
        "status": AppointmentStatus.ACTIVE,
    }
    defaults.update(kwargs)
    return Appointment(**defaults)


# ── Создание записи ───────────────────────────────────────────────────────────

class TestCreateBooking:
    def test_success(self, service: AppointmentService, mock_appointment_repo: MagicMock, mock_schedule_repo: MagicMock) -> None:
        """Успешное создание записи через mock-репозиторий."""
        dto = make_dto()
        result = service.create_booking(dto)

        assert isinstance(result, BookingResultDTO)
        assert result.appointment_id == 1
        assert result.client_name == "Тест"
        assert result.date == "2026-12-01"
        assert result.time == "10:00"
        mock_schedule_repo.book_slot.assert_called_once_with("2026-12-01", "10:00")
        mock_appointment_repo.create.assert_called_once()

    def test_slot_already_booked(self, service: AppointmentService, mock_schedule_repo: MagicMock) -> None:
        """Слот занят — выбрасывает SlotAlreadyBookedError."""
        mock_schedule_repo.book_slot.return_value = False
        with pytest.raises(SlotAlreadyBookedError) as exc_info:
            service.create_booking(make_dto())
        assert exc_info.value.date == "2026-12-01"
        assert exc_info.value.time == "10:00"

    def test_max_appointments_reached(self, service: AppointmentService, mock_appointment_repo: MagicMock) -> None:
        """Превышен лимит записей — MaxAppointmentsReachedError."""
        mock_appointment_repo.count_active_by_user_id.return_value = 1
        with pytest.raises(MaxAppointmentsReachedError) as exc_info:
            service.create_booking(make_dto())
        assert exc_info.value.max_count == 1

    def test_blacklisted_user(self, service: AppointmentService, mock_appointment_repo: MagicMock) -> None:
        """Заблокированный пользователь — BlacklistedUserError."""
        mock_appointment_repo.is_user_blocked.return_value = True
        with pytest.raises(BlacklistedUserError) as exc_info:
            service.create_booking(make_dto())
        assert exc_info.value.user_id == 123

    def test_with_service_and_comment(self, service: AppointmentService, mock_appointment_repo: MagicMock) -> None:
        """Создание записи с услугой и комментарием."""
        dto = make_dto(service="маникюр", comment="Тест комментарий")
        result = service.create_booking(dto)
        assert result.appointment_id == 1

    def test_create_appointment_wrapper(self, service: AppointmentService) -> None:
        """create_appointment — обёртка над create_booking."""
        appt_id = service.create_appointment(
            user_telegram_id=123,
            date_str="2026-12-01",
            time_str="10:00",
            client_name="Тест",
            phone="+79991234567",
        )
        assert appt_id == 1


# ── Отмена записи ─────────────────────────────────────────────────────────────

class TestCancelAppointment:
    def test_cancel_by_user_success(
        self,
        service: AppointmentService,
        mock_appointment_repo: MagicMock,
        mock_schedule_repo: MagicMock,
    ) -> None:
        """Клиент успешно отменяет свою запись."""
        appt = make_appointment()
        mock_appointment_repo.get_active_by_user_id.return_value = appt
        mock_schedule_repo.release_slot.return_value = []

        result = service.cancel_by_user(123)

        assert result is not None
        mock_appointment_repo.cancel.assert_called_once_with(1)
        mock_schedule_repo.release_slot.assert_called_once_with("2026-12-01", "10:00")

    def test_cancel_by_user_no_appointment(
        self, service: AppointmentService, mock_appointment_repo: MagicMock
    ) -> None:
        """Нет активной записи — возвращает None."""
        mock_appointment_repo.get_active_by_user_id.return_value = None
        result = service.cancel_by_user(123)
        assert result is None

    def test_cancel_by_id_success(
        self,
        service: AppointmentService,
        mock_appointment_repo: MagicMock,
        mock_schedule_repo: MagicMock,
    ) -> None:
        """Отмена записи по ID."""
        appt = make_appointment()
        mock_appointment_repo.get_by_id.return_value = appt
        mock_schedule_repo.release_slot.return_value = []

        result = service.cancel_by_id(1)
        assert result is not None
        mock_appointment_repo.cancel.assert_called_once_with(1)

    def test_cancel_by_id_not_found(
        self, service: AppointmentService, mock_appointment_repo: MagicMock
    ) -> None:
        """Запись не найдена — AppointmentNotFoundError."""
        mock_appointment_repo.get_by_id.return_value = None
        with pytest.raises(AppointmentNotFoundError):
            service.cancel_by_id(999)

    def test_cancel_by_id_already_cancelled(
        self, service: AppointmentService, mock_appointment_repo: MagicMock
    ) -> None:
        """Запись уже отменена — AppointmentAlreadyCancelledError."""
        appt = make_appointment(status=AppointmentStatus.CANCELLED)
        mock_appointment_repo.get_by_id.return_value = appt
        with pytest.raises(AppointmentAlreadyCancelledError) as exc_info:
            service.cancel_by_id(1)
        assert exc_info.value.appointment_id == 1

    def test_cancel_appointment_wrong_user(
        self, service: AppointmentService, mock_appointment_repo: MagicMock
    ) -> None:
        """Попытка отменить чужую запись — AppointmentNotFoundError."""
        appt = make_appointment(user_id=999)  # другой пользователь
        mock_appointment_repo.get_by_id.return_value = appt
        with pytest.raises(AppointmentNotFoundError):
            service.cancel_appointment(1, user_id=123)


# ── Чтение записей ────────────────────────────────────────────────────────────

class TestReadAppointments:
    def test_get_appointment_by_id(
        self, service: AppointmentService, mock_appointment_repo: MagicMock
    ) -> None:
        appt = make_appointment()
        mock_appointment_repo.get_by_id.return_value = appt
        result = service.get_appointment_by_id(1)
        assert result is appt

    def test_get_appointment_by_id_not_found(
        self, service: AppointmentService, mock_appointment_repo: MagicMock
    ) -> None:
        mock_appointment_repo.get_by_id.return_value = None
        result = service.get_appointment_by_id(999)
        assert result is None

    def test_get_user_appointments(
        self, service: AppointmentService, mock_appointment_repo: MagicMock
    ) -> None:
        appts = [make_appointment(), make_appointment(id=2, time="11:00")]
        mock_appointment_repo.get_active_list_by_user_id.return_value = appts
        result = service.get_user_appointments(123)
        assert len(result) == 2

    def test_get_appointments_filtered_today(
        self, service: AppointmentService, mock_appointment_repo: MagicMock
    ) -> None:
        mock_appointment_repo.get_by_date.return_value = []
        result = service.get_appointments_filtered("today")
        mock_appointment_repo.get_by_date.assert_called_once()
        assert result == []

    def test_get_appointments_filtered_all(
        self, service: AppointmentService, mock_appointment_repo: MagicMock
    ) -> None:
        mock_appointment_repo.get_all.return_value = []
        service.get_appointments_filtered("all")
        mock_appointment_repo.get_all.assert_called_once()


# ── Статистика ────────────────────────────────────────────────────────────────

class TestGetStatistics:
    def test_get_statistics(
        self, service: AppointmentService, mock_appointment_repo: MagicMock
    ) -> None:
        expected = {"total": 10, "confirmed": 7, "cancelled": 3, "today": 2, "week": 5}
        mock_appointment_repo.get_statistics_raw.return_value = expected
        stats = service.get_statistics()
        assert stats == expected
        mock_appointment_repo.get_statistics_raw.assert_called_once()

    def test_get_statistics_empty_db(
        self, service: AppointmentService, mock_appointment_repo: MagicMock
    ) -> None:
        mock_appointment_repo.get_statistics_raw.return_value = {
            "total": 0, "confirmed": 0, "cancelled": 0, "today": 0, "week": 0,
        }
        stats = service.get_statistics()
        assert stats["total"] == 0


# ── Чёрный список ─────────────────────────────────────────────────────────────

class TestBlacklist:
    def test_block_user(
        self, service: AppointmentService, mock_appointment_repo: MagicMock
    ) -> None:
        service.block_user(123, "Тест")
        mock_appointment_repo.block_user.assert_called_once_with(123, "Тест")

    def test_unblock_user(
        self, service: AppointmentService, mock_appointment_repo: MagicMock
    ) -> None:
        service.unblock_user(123)
        mock_appointment_repo.unblock_user.assert_called_once_with(123)

    def test_is_user_blocked_true(
        self, service: AppointmentService, mock_appointment_repo: MagicMock
    ) -> None:
        mock_appointment_repo.is_user_blocked.return_value = True
        assert service.is_user_blocked(123) is True

    def test_is_user_blocked_false(
        self, service: AppointmentService, mock_appointment_repo: MagicMock
    ) -> None:
        mock_appointment_repo.is_user_blocked.return_value = False
        assert service.is_user_blocked(456) is False


# ── Waitlist-уведомление ──────────────────────────────────────────────────────

class TestWaitlistNotification:
    def test_notification_callback_called_on_cancel(
        self,
        mock_appointment_repo: MagicMock,
        mock_schedule_repo: MagicMock,
    ) -> None:
        """При отмене записи срабатывает callback для уведомления waitlist."""
        notified: list[tuple] = []

        def callback(user_id: int, date: str, time: str) -> None:
            notified.append((user_id, date, time))

        svc = AppointmentService(
            appointment_repo=mock_appointment_repo,
            schedule_repo=mock_schedule_repo,
            max_per_user=1,
            notification_callback=callback,
        )

        appt = make_appointment()
        mock_appointment_repo.get_active_by_user_id.return_value = appt
        # release_slot возвращает [(user_id, time)] для waitlist
        mock_schedule_repo.release_slot.return_value = [(999, "10:00")]

        svc.cancel_by_user(123)

        assert len(notified) == 1
        assert notified[0] == (999, "2026-12-01", "10:00")
