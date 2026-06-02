"""
src/application/use_cases/ — Use Cases слой (Clean Architecture).

FIXED H-06: директория была пустой, нарушая заявленную Clean Architecture.
Теперь содержит базовые Use Cases, делегирующие в соответствующие сервисы.

Архитектурное решение: Use Cases действуют как тонкий оркестрирующий слой
между хендлерами (Presentation) и сервисами (Application).
Хендлеры должны вызывать Use Cases, а не сервисы напрямую.
"""

from src.application.use_cases.booking_use_cases import (
    CancelBookingUseCase,
    CreateBookingUseCase,
    GetUserAppointmentsUseCase,
)

__all__ = [
    "CreateBookingUseCase",
    "CancelBookingUseCase",
    "GetUserAppointmentsUseCase",
]
