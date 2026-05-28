"""
src/application/dto/booking_dto.py — Data Transfer Objects.

✅ Из v2_zip + v2_tar: CreateBookingDTO, BookingResultDTO
✅ Улучшения v4: AddWorkingDayDTO, AddSlotDTO, frozen dataclasses для безопасности
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True, slots=True)
class CreateBookingDTO:
    """DTO для создания записи клиентом."""
    user_id: int
    client_name: str
    phone: str
    date: str
    time: str
    username: Optional[str] = None
    comment: Optional[str] = None


@dataclass(frozen=True, slots=True)
class BookingResultDTO:
    """DTO результата создания записи."""
    appointment_id: int
    client_name: str
    date: str
    time: str


@dataclass(frozen=True, slots=True)
class AddWorkingDayDTO:
    """DTO для добавления рабочего дня."""
    date: str
    default_slots: Tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AddSlotDTO:
    """DTO для добавления временного слота."""
    date: str
    time: str
