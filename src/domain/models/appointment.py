"""
src/domain/models/appointment.py — Доменная модель «Запись».

Атрибуты:
    user_id:        Telegram ID клиента.
    client_name:    Имя клиента.
    phone:          Номер телефона клиента.
    date:           Дата приёма «YYYY-MM-DD».
    time:           Время приёма «HH:MM».
    id:             Уникальный идентификатор (None до сохранения в БД).
    username:       Telegram username клиента (опционально).
    created_at:     Метка времени создания записи.
    reminder_sent:  Отправлено ли напоминание.
    status:         Текущий статус записи.
    comment:        Комментарий клиента (опционально).
    service:        Название услуги (опционально).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from src.domain.enums import AppointmentStatus

# Паттерн для валидации времени «HH:MM»
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")
# Паттерн для валидации даты «YYYY-MM-DD»
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(slots=True)
class Appointment:
    """Запись клиента на приём."""

    user_id: int
    client_name: str
    phone: str
    date: str
    time: str
    id: int | None = field(default=None)
    username: str | None = field(default=None)
    created_at: datetime | None = field(default=None)
    reminder_sent: bool = field(default=False)
    status: AppointmentStatus = field(default=AppointmentStatus.ACTIVE)
    comment: str | None = field(default=None)
    service: str | None = field(default=None)

    def __post_init__(self) -> None:
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now())
        # Базовая валидация форматов
        if self.date and not _DATE_RE.match(self.date):
            raise ValueError(f"Invalid date format: {self.date!r}, expected YYYY-MM-DD")
        if self.time and not _TIME_RE.match(self.time):
            raise ValueError(f"Invalid time format: {self.time!r}, expected HH:MM")

    @property
    def is_active(self) -> bool:
        """True если запись активна (не отменена)."""
        return self.status == AppointmentStatus.ACTIVE

    @property
    def is_cancelled(self) -> bool:
        """True если запись отменена."""
        return self.status == AppointmentStatus.CANCELLED

    @property
    def is_completed(self) -> bool:
        """True если запись выполнена (клиент пришёл)."""
        return self.status == AppointmentStatus.COMPLETED

    @property
    def datetime(self) -> datetime:
        """datetime объекта из даты и времени записи."""
        return datetime.strptime(f"{self.date} {self.time}", "%Y-%m-%d %H:%M")

    def cancel(self) -> None:
        """Отменяет запись."""
        if self.status == AppointmentStatus.CANCELLED:
            raise ValueError(f"Appointment #{self.id} is already cancelled")
        self.status = AppointmentStatus.CANCELLED

    def complete(self) -> None:
        """Помечает запись как выполненную."""
        if self.status == AppointmentStatus.CANCELLED:
            raise ValueError(f"Cannot complete cancelled appointment #{self.id}")
        self.status = AppointmentStatus.COMPLETED

    def mark_reminder_sent(self) -> None:
        """Помечает напоминание отправленным."""
        self.reminder_sent = True

    @classmethod
    def from_row(cls, row: dict) -> Appointment:
        """Создаёт экземпляр из строки БД.

        Args:
            row: Словарь с данными из БД.

        Returns:
            Экземпляр Appointment.

        Raises:
            KeyError: Если в строке отсутствуют обязательные поля.
        """
        created_at: datetime | None = None
        if row.get("created_at"):
            try:
                created_at = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                created_at = None

        return cls(
            id=row["id"],
            user_id=row["user_id"],
            username=row.get("username"),
            client_name=row["client_name"],
            phone=row["phone"],
            date=row["date"],
            time=row["time"],
            created_at=created_at,
            reminder_sent=bool(row.get("reminder_sent", 0)),
            # Безопасная загрузка статуса через from_db_value()
            status=AppointmentStatus.from_db_value(row.get("is_cancelled", 0)),
            comment=row.get("comment"),
            service=row.get("service"),
        )

    def to_dict(self) -> dict:
        """Сериализует объект в словарь для хранения в БД."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.username,
            "client_name": self.client_name,
            "phone": self.phone,
            "date": self.date,
            "time": self.time,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
            "reminder_sent": int(self.reminder_sent),
            "is_cancelled": int(self.status),
            "comment": self.comment,
            "service": self.service,
        }

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Appointment):
            return NotImplemented
        if self.id is not None and other.id is not None:
            return self.id == other.id
        return (
            self.user_id == other.user_id
            and self.date == other.date
            and self.time == other.time
        )

    def __repr__(self) -> str:
        return (
            f"Appointment(id={self.id}, user_id={self.user_id}, "
            f"date={self.date!r}, time={self.time!r}, status={self.status.name})"
        )
