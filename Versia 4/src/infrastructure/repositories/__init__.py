"""src/infrastructure/repositories/__init__.py"""
from src.infrastructure.repositories.appointment_repository import AppointmentRepository
from src.infrastructure.repositories.schedule_repository import ScheduleRepository

__all__ = ["AppointmentRepository", "ScheduleRepository"]
