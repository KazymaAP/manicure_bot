"""
tests/unit/test_domain/test_booking_dto.py
Unit-тесты для CreateBookingDTO — валидация форматов.
"""
import pytest

from src.application.dto.booking_dto import CreateBookingDTO


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


class TestCreateBookingDTO:
    def test_valid_dto(self):
        """Корректный DTO создаётся без ошибок."""
        dto = make_dto()
        assert dto.user_id == 123
        assert dto.date == "2026-12-01"
        assert dto.time == "10:00"

    def test_invalid_date_format(self):
        """Некорректный формат даты вызывает ValueError."""
        with pytest.raises(ValueError, match="Invalid date format"):
            make_dto(date="01.12.2026")

    def test_invalid_date_value(self):
        """Несуществующая дата вызывает ValueError."""
        with pytest.raises(ValueError, match="Invalid date"):
            make_dto(date="2026-13-01")

    def test_invalid_time_format(self):
        """Некорректный формат времени вызывает ValueError."""
        with pytest.raises(ValueError, match="Invalid time format"):
            make_dto(time="10:00:00")

    def test_invalid_time_range(self):
        """Время вне диапазона вызывает ValueError."""
        with pytest.raises(ValueError, match="out of range"):
            make_dto(time="25:00")

    def test_invalid_phone(self):
        """Некорректный телефон вызывает ValueError."""
        with pytest.raises(ValueError, match="Invalid phone"):
            make_dto(phone="not-a-phone")

    def test_dto_is_frozen(self):
        """DTO неизменяем (frozen dataclass)."""
        dto = make_dto()
        with pytest.raises((AttributeError, TypeError)):
            dto.user_id = 999  # type: ignore[misc]

    def test_optional_fields_default_to_none(self):
        """Необязательные поля по умолчанию равны None."""
        dto = make_dto()
        assert dto.username is None
        assert dto.comment is None
        assert dto.service is None
