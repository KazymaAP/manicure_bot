"""
tests/unit/test_domain/test_appointment_status.py
Unit-тесты для AppointmentStatus enum.
"""
import pytest

from src.domain.enums.appointment_status import AppointmentStatus


class TestAppointmentStatus:
    def test_known_values(self):
        """Проверка известных значений enum."""
        assert AppointmentStatus.ACTIVE == 0
        assert AppointmentStatus.CANCELLED == 1
        assert AppointmentStatus.COMPLETED == 2

    def test_from_db_value_known(self):
        """from_db_value корректно возвращает известные статусы."""
        assert AppointmentStatus.from_db_value(0) == AppointmentStatus.ACTIVE
        assert AppointmentStatus.from_db_value(1) == AppointmentStatus.CANCELLED
        assert AppointmentStatus.from_db_value(2) == AppointmentStatus.COMPLETED

    def test_from_db_value_unknown_returns_active(self):
        """from_db_value возвращает ACTIVE для неизвестных значений (защитный fallback)."""
        result = AppointmentStatus.from_db_value(99)
        assert result == AppointmentStatus.ACTIVE

    def test_from_db_value_negative(self):
        """from_db_value возвращает ACTIVE для отрицательных значений."""
        result = AppointmentStatus.from_db_value(-1)
        assert result == AppointmentStatus.ACTIVE
