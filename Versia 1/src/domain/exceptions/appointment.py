"""
src/domain/exceptions/appointment.py — Исключения для записей.

Все доменные исключения наследуются от DomainError и содержат
человекочитаемые сообщения для логирования.
"""
from __future__ import annotations

from src.domain.exceptions.base import DomainError


class AppointmentNotFoundError(DomainError):
    """Запись не найдена в базе данных."""

    def __init__(self, appointment_id: int) -> None:
        super().__init__(f"Appointment #{appointment_id} not found")
        self.appointment_id = appointment_id


class AppointmentAlreadyCancelledError(DomainError):
    """Запись существует, но уже была отменена ранее.

    Семантически отличается от AppointmentNotFoundError — запись найдена в БД,
    просто уже имеет статус CANCELLED. Вызывающий код может показать корректное
    сообщение: «Запись уже отменена» вместо «Запись не найдена».
    """

    def __init__(self, appointment_id: int) -> None:
        super().__init__(f"Appointment #{appointment_id} is already cancelled")
        self.appointment_id = appointment_id


class AppointmentAlreadyExistsError(DomainError):
    """Пользователь уже имеет активную запись."""

    def __init__(self, user_id: int) -> None:
        super().__init__(f"User {user_id} already has an active appointment")
        self.user_id = user_id


class SlotAlreadyBookedError(DomainError):
    """Указанный временной слот уже занят."""

    def __init__(self, date: str, time: str) -> None:
        super().__init__(f"Slot {date} {time} is already booked")
        self.date = date
        self.time = time


class MaxAppointmentsReachedError(DomainError):
    """Превышен лимит активных записей для пользователя."""

    def __init__(self, max_count: int) -> None:
        super().__init__(f"Maximum number of appointments ({max_count}) reached")
        self.max_count = max_count


class BlacklistedUserError(DomainError):
    """Пользователь находится в чёрном списке."""

    def __init__(self, user_id: int) -> None:
        super().__init__(f"User {user_id} is blacklisted and cannot create appointments")
        self.user_id = user_id
