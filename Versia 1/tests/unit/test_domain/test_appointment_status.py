"""
tests/unit/test_domain/test_appointment_status.py
Unit-тесты для AppointmentStatus enum.
"""
from __future__ import annotations

from src.domain.enums.appointment_status import AppointmentStatus


class TestAppointmentStatus:
    def test_active_value(self) -> None:
        assert AppointmentStatus.ACTIVE == 0

    def test_cancelled_value(self) -> None:
        assert AppointmentStatus.CANCELLED == 1

    def test_completed_value(self) -> None:
        assert AppointmentStatus.COMPLETED == 2

    def test_from_db_value_active(self) -> None:
        assert AppointmentStatus.from_db_value(0) == AppointmentStatus.ACTIVE

    def test_from_db_value_cancelled(self) -> None:
        assert AppointmentStatus.from_db_value(1) == AppointmentStatus.CANCELLED

    def test_from_db_value_completed(self) -> None:
        assert AppointmentStatus.from_db_value(2) == AppointmentStatus.COMPLETED

    def test_from_db_value_none(self) -> None:
        """None → ACTIVE (безопасный fallback)."""
        assert AppointmentStatus.from_db_value(None) == AppointmentStatus.ACTIVE

    def test_from_db_value_unknown(self) -> None:
        """Неизвестное значение → ACTIVE (безопасный fallback)."""
        assert AppointmentStatus.from_db_value(99) == AppointmentStatus.ACTIVE

    def test_from_db_value_negative(self) -> None:
        assert AppointmentStatus.from_db_value(-1) == AppointmentStatus.ACTIVE

    def test_label_active(self) -> None:
        assert AppointmentStatus.ACTIVE.label == "Активна"

    def test_label_cancelled(self) -> None:
        assert AppointmentStatus.CANCELLED.label == "Отменена"

    def test_label_completed(self) -> None:
        assert AppointmentStatus.COMPLETED.label == "Выполнена"

    def test_int_comparison(self) -> None:
        """IntEnum позволяет сравнивать с целыми числами."""
        assert AppointmentStatus.ACTIVE == 0
        assert AppointmentStatus.CANCELLED == 1
        assert int(AppointmentStatus.COMPLETED) == 2
