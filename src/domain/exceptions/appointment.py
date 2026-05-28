"""
src/domain/exceptions/appointment.py — Исключения для записей.
"""
from src.domain.exceptions.base import DomainError


class AppointmentNotFoundError(DomainError):
    def __init__(self, appointment_id: int) -> None:
        super().__init__(f"Appointment #{appointment_id} not found")
        self.appointment_id = appointment_id


class AppointmentAlreadyExistsError(DomainError):
    def __init__(self, user_id: int) -> None:
        super().__init__(f"User {user_id} already has an active appointment")
        self.user_id = user_id


class SlotAlreadyBookedError(DomainError):
    def __init__(self, date: str, time: str) -> None:
        super().__init__(f"Slot {date} {time} is already booked")
        self.date = date
        self.time = time


class MaxAppointmentsReachedError(DomainError):
    def __init__(self, max_count: int) -> None:
        super().__init__(f"Maximum number of appointments ({max_count}) reached")
        self.max_count = max_count
