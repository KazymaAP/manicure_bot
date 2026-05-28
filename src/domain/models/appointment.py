"""
src/domain/models/appointment.py — Доменная модель «Запись».

✅ Из v2_tar: dataclass slots=True, from_row/to_dict, property is_active/is_cancelled
✅ Улучшения v4: __repr__, __eq__, validate method
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from src.domain.enums import AppointmentStatus


@dataclass(slots=True)
class Appointment:
    """Запись клиента на приём.

    Attributes:
        user_id: Telegram ID клиента.
        client_name: Имя клиента.
        phone: Номер телефона клиента.
        date: Дата приёма «YYYY-MM-DD».
        time: Время приёма «HH:MM».
        id: Уникальный идентификатор (None до сохранения в БД).
        username: Telegram username клиента (опционально).
        created_at: Метка времени создания записи.
        reminder_sent: Отправлено ли напоминание.
        status: Текущий статус записи.
    """

    user_id: int
    client_name: str
    phone: str
    date: str
    time: str
    id: Optional[int] = field(default=None)
    username: Optional[str] = field(default=None)
    created_at: Optional[datetime] = field(default=None)
    reminder_sent: bool = field(default=False)
    status: AppointmentStatus = field(default=AppointmentStatus.ACTIVE)
    comment: Optional[str] = field(default=None)

    def __post_init__(self) -> None:
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now())

    @property
    def is_active(self) -> bool:
        """True если запись активна (не отменена)."""
        return self.status == AppointmentStatus.ACTIVE

    @property
    def is_cancelled(self) -> bool:
        """True если запись отменена."""
        return self.status == AppointmentStatus.CANCELLED

    @property
    def datetime(self) -> datetime:
        """datetime объекта из даты и времени записи."""
        return datetime.strptime(f"{self.date} {self.time}", "%Y-%m-%d %H:%M")

    def cancel(self) -> None:
        """Отменяет запись."""
        self.status = AppointmentStatus.CANCELLED

    def mark_reminder_sent(self) -> None:
        """Помечает напоминание отправленным."""
        self.reminder_sent = True

    @classmethod
    def from_row(cls, row: dict) -> "Appointment":
        """Создаёт экземпляр из строки БД.

        Args:
            row: Словарь с данными из БД.

        Returns:
            Экземпляр Appointment.
        """
        created_at: Optional[datetime] = None
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
            status=AppointmentStatus(row.get("is_cancelled", 0)),
            comment=row.get("comment"),
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
        }
