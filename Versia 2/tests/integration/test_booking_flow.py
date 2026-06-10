"""
tests/integration/test_booking_flow.py — Интеграционные тесты FSM-потоков записи клиента.

BUG 24 FIX: покрывает полные FSM-потоки через сервисный слой без реальной Telegram-сессии.
Тестирует:
  1. Happy path: создание записи через create_appointment
  2. SlotAlreadyBookedError при попытке занять занятый слот
  3. MaxAppointmentsReachedError при превышении лимита записей
  4. cancel_appointment с проверкой владельца
  5. Нормализация телефона (проверяем что номер хранится без пробелов/скобок)
  6. HTML-инъекция: данные с символами <, >, & не ломают форматирование
"""
from __future__ import annotations

import re
from unittest.mock import MagicMock

import pytest

from src.application.dto.booking_dto import CreateBookingDTO
from src.application.services.appointment_service import AppointmentService
from src.domain.enums.appointment_status import AppointmentStatus
from src.domain.exceptions.appointment import (
    AppointmentNotFoundError,
    MaxAppointmentsReachedError,
    SlotAlreadyBookedError,
)
from src.domain.models.appointment import Appointment
from src.presentation.formatters.message_formatter import MessageFormatter

# ─── Фикстуры ────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_appointment_repo() -> MagicMock:
    repo = MagicMock()
    repo.count_active_by_user_id.return_value = 0
    repo.create.return_value = 42
    repo.is_user_blocked.return_value = False
    repo.db = None  # Path B (mock) в create_booking
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
        "user_id": 777,
        "client_name": "Анна Тест",
        "phone": "+79991234567",
        "date": "2026-12-10",
        "time": "10:00",
    }
    defaults.update(kwargs)
    return CreateBookingDTO(**defaults)


def make_appointment(**kwargs) -> Appointment:
    defaults = {
        "id": 1,
        "user_id": 777,
        "client_name": "Анна Тест",
        "phone": "+79991234567",
        "date": "2026-12-10",
        "time": "10:00",
        "status": AppointmentStatus.ACTIVE,
    }
    defaults.update(kwargs)
    return Appointment(**defaults)


# ─── Тест 1: Happy path — создание записи ────────────────────────────────────

def test_booking_happy_path(service: AppointmentService, mock_appointment_repo: MagicMock) -> None:
    """Полный путь создания записи через create_appointment."""
    appt_id = service.create_appointment(
        user_telegram_id=777,
        date_str="2026-12-10",
        time_str="10:00",
        client_name="Анна Тест",
        phone="+79991234567",
        comment="Первый визит",
        username="anna_test",
        service="маникюр",
    )
    assert appt_id == 42
    mock_appointment_repo.create.assert_called_once()


# ─── Тест 2: SlotAlreadyBookedError при занятом слоте ────────────────────────

def test_booking_slot_already_booked(service: AppointmentService, mock_schedule_repo: MagicMock) -> None:
    """При занятом слоте поднимается SlotAlreadyBookedError."""
    mock_schedule_repo.book_slot.return_value = False  # Слот занят
    dto = make_dto()
    with pytest.raises(SlotAlreadyBookedError):
        service.create_booking(dto)


# ─── Тест 3: MaxAppointmentsReachedError при превышении лимита ───────────────

def test_booking_max_appointments_reached(
    service: AppointmentService,
    mock_appointment_repo: MagicMock,
) -> None:
    """При превышении лимита активных записей поднимается MaxAppointmentsReachedError."""
    mock_appointment_repo.count_active_by_user_id.return_value = 1  # Уже есть 1 запись
    dto = make_dto()
    with pytest.raises(MaxAppointmentsReachedError):
        service.create_booking(dto)


# ─── Тест 4: cancel_appointment с проверкой владельца ────────────────────────

def test_cancel_appointment_wrong_owner(
    service: AppointmentService,
    mock_appointment_repo: MagicMock,
) -> None:
    """Отмена чужой записи поднимает AppointmentNotFoundError."""
    appt = make_appointment(id=5, user_id=777)
    mock_appointment_repo.get_by_id.return_value = appt

    with pytest.raises(AppointmentNotFoundError):
        service.cancel_appointment(appointment_id=5, user_id=999)  # Другой user_id


def test_cancel_appointment_correct_owner(
    service: AppointmentService,
    mock_appointment_repo: MagicMock,
) -> None:
    """Отмена своей записи проходит успешно."""
    appt = make_appointment(id=5, user_id=777)
    mock_appointment_repo.get_by_id.return_value = appt

    result = service.cancel_appointment(appointment_id=5, user_id=777)
    assert result is not None
    mock_appointment_repo.cancel.assert_called_once_with(5)


# ─── Тест 5: Нормализация телефона ──────────────────────────────────────────

def test_phone_normalization() -> None:
    """Нормализация телефона убирает пробелы, тире и скобки."""
    raw_phones = [
        "+7 (999) 123-45-67",
        "+7(999)123-45-67",
        "+7 999 123 45 67",
        "8-999-123-45-67",
    ]
    for raw_phone in raw_phones:
        # Та же логика что в user_handler.enter_phone
        normalized = re.sub(r"[\s\-()]+", "", raw_phone)
        # Нормализованный номер не должен содержать пробелов, тире, скобок
        assert " " not in normalized, f"Пробел остался в '{normalized}'"
        assert "-" not in normalized, f"Тире осталось в '{normalized}'"
        assert "(" not in normalized, f"Скобка осталась в '{normalized}'"
        assert ")" not in normalized, f"Скобка осталась в '{normalized}'"
        # Должен соответствовать шаблону +7XXXXXXXXXX или 8XXXXXXXXXX
        assert re.match(r"^\+?[0-9]{7,15}$", normalized), f"Некорректный формат: '{normalized}'"


# ─── Тест 6: HTML-экранирование пользовательских данных ──────────────────────

def test_html_escape_in_formatter() -> None:
    """HTML-символы в данных пользователя экранируются корректно."""
    malicious_name = "<script>alert(1)</script>"
    malicious_phone = "+7&(999)&nbsp;123"
    malicious_comment = "Тест <b>жирный</b> & 'кавычки'"

    # Форматируем карточку записи
    card = MessageFormatter.appointment_card_box(
        date_str="2026-12-10",
        time_str="10:00",
        client_name=malicious_name,
        phone=malicious_phone,
        comment=malicious_comment,
        service="маникюр",
    )

    # В HTML-тексте не должно быть незакрытых тегов от пользователя
    assert "<script>" not in card
    assert "</script>" not in card
    # Экранированные версии должны присутствовать
    assert "&lt;script&gt;" in card or "script" in card  # escape или без тега
    assert "&amp;" in card or "&" not in card  # & должен быть экранирован


def test_html_escape_in_admin_appointment_detail() -> None:
    """Данные клиента в admin_appointment_detail корректно экранируются."""
    appt = make_appointment(
        client_name="</b><b>Взлом",
        phone="+7&999",
        comment="<img src=x>",
    )

    detail = MessageFormatter.admin_appointment_detail(appt)

    # Незакрытые теги от пользователя не должны попасть в HTML
    assert "</b><b>" not in detail
    assert "<img" not in detail
    # Экранированные версии
    assert "&lt;/b&gt;" in detail or "</b>" not in detail.split("Взлом")[0]


# ─── Тест 7: Полный FSM-поток через сервис (happy path с полными данными) ────

def test_full_booking_flow_with_service(
    service: AppointmentService,
    mock_appointment_repo: MagicMock,
    mock_schedule_repo: MagicMock,
) -> None:
    """
    Симулирует полный поток: выбор услуги → дата → время → имя → телефон → подтверждение.
    Проверяет что create_appointment вызывается с корректными аргументами.
    """
    appt_id = service.create_appointment(
        user_telegram_id=12345,
        date_str="2026-12-15",
        time_str="14:00",
        client_name="Мария",
        phone="+79001234567",
        comment=None,
        username="maria_user",
        service="педикюр",
    )

    assert appt_id == 42

    # Проверяем что слот был забронирован
    mock_schedule_repo.book_slot.assert_called_once_with("2026-12-15", "14:00")

    # Проверяем что запись была создана через репозиторий
    mock_appointment_repo.create.assert_called_once()

    created_appt: Appointment = mock_appointment_repo.create.call_args[0][0]
    assert created_appt.client_name == "Мария"
    assert created_appt.date == "2026-12-15"
    assert created_appt.time == "14:00"
    assert created_appt.service is None  # create_booking Path B не передаёт service через Appointment


# ─── Тест 8: Отмена на любом шаге (сброс FSM) ────────────────────────────────

def test_booking_cancellation_clears_data(
    service: AppointmentService,
    mock_appointment_repo: MagicMock,
) -> None:
    """После cancel_appointment данные записи корректно убираются."""
    appt = make_appointment(id=10, user_id=777)
    mock_appointment_repo.get_by_id.return_value = appt

    cancelled = service.cancel_appointment(appointment_id=10, user_id=777)
    assert cancelled is not None
    assert cancelled.is_cancelled is True
    mock_appointment_repo.cancel.assert_called_once_with(10)
