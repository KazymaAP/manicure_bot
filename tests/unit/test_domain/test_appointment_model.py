"""
tests/unit/test_domain/test_appointment_model.py
Unit-тесты для модели Appointment.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from src.domain.enums.appointment_status import AppointmentStatus
from src.domain.models.appointment import Appointment


def make_appointment(**kwargs) -> Appointment:
    defaults = dict(
        id=1,
        user_id=123,
        client_name="Тест Тестов",
        phone="+79991234567",
        date="2026-12-01",
        time="10:00",
        status=AppointmentStatus.ACTIVE,
    )
    defaults.update(kwargs)
    return Appointment(**defaults)


class TestAppointmentStatus:
    def test_is_active_true(self) -> None:
        appt = make_appointment(status=AppointmentStatus.ACTIVE)
        assert appt.is_active is True
        assert appt.is_cancelled is False
        assert appt.is_completed is False

    def test_is_cancelled_true(self) -> None:
        appt = make_appointment(status=AppointmentStatus.CANCELLED)
        assert appt.is_cancelled is True
        assert appt.is_active is False

    def test_is_completed_true(self) -> None:
        appt = make_appointment(status=AppointmentStatus.COMPLETED)
        assert appt.is_completed is True
        assert appt.is_active is False

    def test_cancel_changes_status(self) -> None:
        appt = make_appointment()
        appt.cancel()
        assert appt.status == AppointmentStatus.CANCELLED
        assert appt.is_cancelled is True

    def test_cancel_already_cancelled_raises(self) -> None:
        """Повторная отмена — ValueError."""
        appt = make_appointment(status=AppointmentStatus.CANCELLED)
        with pytest.raises(ValueError):
            appt.cancel()

    def test_complete_changes_status(self) -> None:
        appt = make_appointment()
        appt.complete()
        assert appt.status == AppointmentStatus.COMPLETED
        assert appt.is_completed is True

    def test_complete_cancelled_raises(self) -> None:
        """Завершить отменённую запись нельзя."""
        appt = make_appointment(status=AppointmentStatus.CANCELLED)
        with pytest.raises(ValueError):
            appt.complete()

    def test_mark_reminder_sent(self) -> None:
        appt = make_appointment()
        assert appt.reminder_sent is False
        appt.mark_reminder_sent()
        assert appt.reminder_sent is True


class TestAppointmentDatetime:
    def test_datetime_property(self) -> None:
        appt = make_appointment(date="2026-12-01", time="14:30")
        expected = datetime(2026, 12, 1, 14, 30)
        assert appt.datetime == expected

    def test_created_at_defaults_to_now(self) -> None:
        appt = make_appointment(id=None, created_at=None)
        assert appt.created_at is not None
        assert isinstance(appt.created_at, datetime)

    def test_invalid_date_format_raises(self) -> None:
        with pytest.raises(ValueError):
            make_appointment(date="01-12-2026")

    def test_invalid_time_format_raises(self) -> None:
        with pytest.raises(ValueError):
            make_appointment(time="10:0")  # неверный формат


class TestAppointmentSerialization:
    def test_from_row_active(self) -> None:
        row = {
            "id": 5,
            "user_id": 100,
            "username": "user100",
            "client_name": "Имя Клиента",
            "phone": "+79001234567",
            "date": "2026-11-15",
            "time": "09:00",
            "created_at": "2026-10-01 12:00:00",
            "reminder_sent": 0,
            "is_cancelled": 0,
            "comment": None,
            "service": "маникюр",
        }
        appt = Appointment.from_row(row)
        assert appt.id == 5
        assert appt.user_id == 100
        assert appt.client_name == "Имя Клиента"
        assert appt.status == AppointmentStatus.ACTIVE
        assert appt.reminder_sent is False
        assert appt.service == "маникюр"

    def test_from_row_cancelled(self) -> None:
        row = {
            "id": 10,
            "user_id": 200,
            "username": None,
            "client_name": "Другой",
            "phone": "+79007654321",
            "date": "2026-11-20",
            "time": "11:00",
            "created_at": None,
            "reminder_sent": 1,
            "is_cancelled": 1,
            "comment": "отмена",
            "service": None,
        }
        appt = Appointment.from_row(row)
        assert appt.status == AppointmentStatus.CANCELLED
        assert appt.is_cancelled is True

    def test_from_row_unknown_status(self) -> None:
        """Неизвестный статус в БД — fallback на ACTIVE."""
        row = {
            "id": 1,
            "user_id": 1,
            "username": None,
            "client_name": "Test",
            "phone": "+7000",
            "date": "2026-11-20",
            "time": "11:00",
            "created_at": None,
            "reminder_sent": 0,
            "is_cancelled": 99,  # неизвестное значение
            "comment": None,
            "service": None,
        }
        appt = Appointment.from_row(row)
        assert appt.status == AppointmentStatus.ACTIVE

    def test_to_dict_roundtrip(self) -> None:
        appt = make_appointment()
        d = appt.to_dict()
        assert d["user_id"] == appt.user_id
        assert d["client_name"] == appt.client_name
        assert d["is_cancelled"] == int(appt.status)
        assert d["reminder_sent"] == 0

    def test_to_dict_after_cancel(self) -> None:
        appt = make_appointment()
        appt.cancel()
        d = appt.to_dict()
        assert d["is_cancelled"] == 1


class TestAppointmentEquality:
    def test_equal_by_id(self) -> None:
        a = make_appointment(id=1)
        b = make_appointment(id=1, client_name="Другое имя")
        assert a == b

    def test_not_equal_different_ids(self) -> None:
        a = make_appointment(id=1)
        b = make_appointment(id=2)
        assert a != b

    def test_repr(self) -> None:
        appt = make_appointment()
        repr_str = repr(appt)
        assert "Appointment" in repr_str
        assert "2026-12-01" in repr_str
