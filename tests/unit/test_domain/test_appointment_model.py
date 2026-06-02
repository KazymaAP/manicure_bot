"""
tests/unit/test_domain/test_appointment_model.py
Unit-тесты для модели Appointment.
"""
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


class TestAppointmentModel:
    def test_is_active_true(self):
        appt = make_appointment(status=AppointmentStatus.ACTIVE)
        assert appt.is_active is True
        assert appt.is_cancelled is False

    def test_is_cancelled_true(self):
        appt = make_appointment(status=AppointmentStatus.CANCELLED)
        assert appt.is_cancelled is True
        assert appt.is_active is False

    def test_cancel_changes_status(self):
        appt = make_appointment()
        appt.cancel()
        assert appt.status == AppointmentStatus.CANCELLED
        assert appt.is_cancelled is True

    def test_mark_reminder_sent(self):
        appt = make_appointment()
        assert appt.reminder_sent is False
        appt.mark_reminder_sent()
        assert appt.reminder_sent is True

    def test_datetime_property(self):
        appt = make_appointment(date="2026-12-01", time="14:30")
        expected = datetime(2026, 12, 1, 14, 30)
        assert appt.datetime == expected

    def test_created_at_defaults_to_now(self):
        appt = make_appointment(id=None, created_at=None)
        assert appt.created_at is not None
        assert isinstance(appt.created_at, datetime)

    def test_from_row(self):
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

    def test_from_row_cancelled(self):
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

    def test_to_dict_roundtrip(self):
        appt = make_appointment()
        d = appt.to_dict()
        assert d["user_id"] == appt.user_id
        assert d["is_cancelled"] == int(appt.status)
