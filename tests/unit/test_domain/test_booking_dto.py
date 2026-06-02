"""
tests/unit/test_domain/test_booking_dto.py
Unit-тесты для CreateBookingDTO и других DTO.
"""
from __future__ import annotations

import dataclasses

import pytest

from src.application.dto.booking_dto import (
    AddSlotDTO,
    AddWorkingDayDTO,
    BookingResultDTO,
    CreateBookingDTO,
)


def make_valid_dto(**kwargs) -> CreateBookingDTO:
    defaults = {
        "user_id": 123,
        "client_name": "Тест Тестов",
        "phone": "+79991234567",
        "date": "2026-12-01",
        "time": "10:00",
    }
    defaults.update(kwargs)
    return CreateBookingDTO(**defaults)


class TestCreateBookingDTO:
    def test_valid_creation(self) -> None:
        dto = make_valid_dto()
        assert dto.user_id == 123
        assert dto.client_name == "Тест Тестов"
        assert dto.phone == "+79991234567"
        assert dto.date == "2026-12-01"
        assert dto.time == "10:00"
        assert dto.comment is None
        assert dto.service is None

    def test_with_optional_fields(self) -> None:
        dto = make_valid_dto(
            username="testuser",
            comment="Тестовый комментарий",
            service="маникюр",
        )
        assert dto.username == "testuser"
        assert dto.comment == "Тестовый комментарий"
        assert dto.service == "маникюр"

    # ── Валидация даты ────────────────────────────────────────────────────

    def test_invalid_date_format_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid date format"):
            make_valid_dto(date="01-12-2026")

    def test_invalid_date_value_raises(self) -> None:
        with pytest.raises(ValueError):
            make_valid_dto(date="2026-13-01")  # месяц 13

    def test_invalid_date_not_date_raises(self) -> None:
        with pytest.raises(ValueError):
            make_valid_dto(date="not-a-date")

    # ── Валидация времени ─────────────────────────────────────────────────

    def test_invalid_time_format_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid time format"):
            make_valid_dto(time="9:00")  # однозначный час

    def test_invalid_time_hour_raises(self) -> None:
        with pytest.raises(ValueError, match="out of range"):
            make_valid_dto(time="25:00")

    def test_invalid_time_minute_raises(self) -> None:
        with pytest.raises(ValueError, match="out of range"):
            make_valid_dto(time="10:60")

    def test_boundary_time_values(self) -> None:
        dto_midnight = make_valid_dto(time="00:00")
        assert dto_midnight.time == "00:00"
        dto_last = make_valid_dto(time="23:59")
        assert dto_last.time == "23:59"

    # ── Валидация имени ───────────────────────────────────────────────────

    def test_name_too_short_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid client_name"):
            make_valid_dto(client_name="A")

    def test_name_too_long_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid client_name"):
            make_valid_dto(client_name="А" * 101)

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid client_name"):
            make_valid_dto(client_name="")

    def test_name_min_length(self) -> None:
        dto = make_valid_dto(client_name="Ал")
        assert dto.client_name == "Ал"

    # ── Валидация телефона ────────────────────────────────────────────────

    def test_invalid_phone_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid phone format"):
            make_valid_dto(phone="not-a-phone")

    def test_phone_too_short_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid phone format"):
            make_valid_dto(phone="123")

    def test_phone_with_formatting(self) -> None:
        """Телефон с пробелами и дефисами должен быть принят."""
        dto = make_valid_dto(phone="+7 999 123-45-67")
        assert dto.phone == "+7 999 123-45-67"

    # ── Валидация комментария ─────────────────────────────────────────────

    def test_comment_too_long_raises(self) -> None:
        with pytest.raises(ValueError, match="Comment is too long"):
            make_valid_dto(comment="x" * 501)

    def test_comment_max_length(self) -> None:
        dto = make_valid_dto(comment="x" * 500)
        assert len(dto.comment) == 500

    def test_frozen_immutable(self) -> None:
        """DTO должен быть неизменяемым (frozen=True)."""
        dto = make_valid_dto()
        with pytest.raises((AttributeError, TypeError, dataclasses.FrozenInstanceError)):
            dto.user_id = 999  # type: ignore[misc]


class TestBookingResultDTO:
    def test_creation(self) -> None:
        result = BookingResultDTO(
            appointment_id=42,
            client_name="Клиент",
            date="2026-12-01",
            time="10:00",
        )
        assert result.appointment_id == 42
        assert result.client_name == "Клиент"

    def test_frozen(self) -> None:
        result = BookingResultDTO(appointment_id=1, client_name="X", date="2026-12-01", time="10:00")
        with pytest.raises((AttributeError, TypeError, dataclasses.FrozenInstanceError)):
            result.appointment_id = 2  # type: ignore[misc]


class TestAddWorkingDayDTO:
    def test_creation(self) -> None:
        dto = AddWorkingDayDTO(date="2026-12-01", default_slots=("09:00", "10:00"))
        assert dto.date == "2026-12-01"
        assert len(dto.default_slots) == 2

    def test_default_empty_slots(self) -> None:
        dto = AddWorkingDayDTO(date="2026-12-01")
        assert dto.default_slots == ()


class TestAddSlotDTO:
    def test_creation(self) -> None:
        dto = AddSlotDTO(date="2026-12-01", time="11:00")
        assert dto.date == "2026-12-01"
        assert dto.time == "11:00"
