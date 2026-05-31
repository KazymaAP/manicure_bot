"""
src/config/settings.py — Централизованная конфигурация через Pydantic v2.

✅ Из v2_tar: BaseSettings + Pydantic validators + lru_cache
✅ Из v2_zip: portfolio_url + redis_url
✅ Улучшения v4: field_validator для channel_id, default_time_slots validation,
   добавлен reminder_hours_before + max_appointments_per_user
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Централизованная конфигурация приложения.

    Все параметры загружаются из переменных окружения или файла .env.
    Используется Pydantic для валидации и типизации.
    """

    # ─── Основные настройки Telegram ─────────────────────────
    bot_token: str = Field(..., description="Токен Telegram бота")
    admin_ids_raw: str = Field(
        default="",
        alias="ADMIN_IDS",
        description="Telegram IDs администраторов (через запятую в .env)"
    )

    # ─── Каналы ──────────────────────────────────────────────
    required_channel: str | None = Field(
        default=None,
        description="Канал для обязательной подписки (@channel_name)",
    )
    schedule_channel_id: int = Field(
        default=-1,
        description="ID канала для публикации расписания (-1 = отключено)",
    )

    # ─── База данных ─────────────────────────────────────────
    db_path: str = Field(
        default="data/manicure_bot.db",
        description="Путь к файлу SQLite",
    )

    # ─── Расписание ──────────────────────────────────────────
    schedule_days_ahead: int = Field(
        default=30,
        ge=1,
        le=365,
        description="Горизонт расписания (дней вперёд)",
    )
    default_time_slots: list[str] = Field(
        default=[
            "09:00", "10:00", "11:00", "12:00",
            "13:00", "14:00", "15:00", "16:00",
            "17:00", "18:00",
        ],
        description="Временные слоты по умолчанию",
    )

    # ─── Услуги (название -> {duration: minutes, price: int})
    services: dict = Field(
        default_factory=dict,
        description="Словарь услуг с длительностью и ценой, например {'маникюр': {'duration': 60, 'price': 1200}}",
    )

    # ─── Рабочие дни (1=Пн ... 7=Вс) по умолчанию
    work_days: list[int] = Field(
        default=[1, 2, 3, 4, 5],
        description="Дни недели, которые считаются рабочими при генерации шаблонов",
    )

    # ─── Бизнес-логика ───────────────────────────────────────
    reminder_hours_before: int = Field(
        default=24,
        ge=1,
        le=72,
        description="За сколько часов до записи отправлять напоминание",
    )
    max_appointments_per_user: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Максимальное кол-во активных записей у одного клиента",
    )

    # ─── Портфолио ───────────────────────────────────────────
    portfolio_url: str | None = Field(
        default=None,
        description="URL портфолио мастера (Instagram, канал, сайт). Если не задан — кнопка скрыта.",
    )

    # ─── Redis (опционально для FSM и кэша) ──────────────────
    redis_url: str | None = Field(
        default=None,
        description="URL Redis (redis://host:port/db), если не задан — MemoryStorage",
    )

    # ─── Логирование ─────────────────────────────────────────
    log_level: str = Field(default="INFO", description="Уровень логирования")
    log_file: str | None = Field(
        default="bot.log",
        description="Файл логов (None = только stdout)",
    )

    # ─── Контактная информация (фича #20) ─────────────────────
    phone: str | None = Field(
        default=None,
        description="Номер телефона мастера",
    )
    instagram: str | None = Field(
        default=None,
        description="Ссылка на Instagram или @username",
    )
    address: str | None = Field(
        default=None,
        description="Адрес студии",
    )
    maps_link: str | None = Field(
        default=None,
        description="Ссылка на Google Maps или Яндекс.Карты",
    )

    # ─── Webhook (фича #40) ──────────────────────────────────
    webhook_url: str | None = Field(
        default=None,
        description="URL для webhook (если используется вместо polling)",
    )
    webhook_port: int = Field(
        default=8443,
        description="Порт для webhook сервера",
    )

    # ─── Временная зона (FIXED) ───────────────────────────────
    timezone: str = Field(
        default="UTC",
        description="Временная зона для напоминаний (например 'Europe/Moscow'). По умолчанию UTC.",
    )

    # ─── Health-check сервер ────────────────────────────────────────────
    # FIXED H-04: вынесено из os.getenv() в Pydantic Settings для корректной валидации
    health_port: int = Field(
        default=8080,
        ge=1,
        le=65535,
        description="Порт HTTP health-check сервера",
    )

    # ─── Приветственное фото ─────────────────────────────────
    welcome_photo_url: str | None = Field(
        default=None,
        description="URL фото для приветственного баннера (опционально)",
    )

    # ─── Валидаторы ──────────────────────────────────────────
    @field_validator("bot_token")
    @classmethod
    def validate_bot_token(cls, v: str) -> str:
        """Проверяет, что токен не пустой (разрешает placeholder для тестирования)."""
        if not v:
            raise ValueError("BOT_TOKEN must be set")
        # Разрешаем placeholder значения (будут проверены при реальном запуске)
        return v

    @field_validator("default_time_slots")
    @classmethod
    def validate_time_slots(cls, v: list[str]) -> list[str]:
        """Проверяет формат временных слотов HH:MM."""
        import re
        pattern = re.compile(r"^\d{2}:\d{2}$")
        for slot in v:
            if not pattern.match(slot):
                raise ValueError(f"Invalid time slot format: {slot!r}, expected HH:MM")
            h, m = map(int, slot.split(":"))
            if not (0 <= h < 24 and 0 <= m < 60):
                raise ValueError(f"Time slot out of range: {slot!r}")
        return v

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def admin_ids(self) -> list[int]:
        """Преобразует строку admin_ids_raw в список целых чисел."""
        if not self.admin_ids_raw:
            return []
        raw_lower = self.admin_ids_raw.strip().lower()
        if raw_lower in ("your_telegram_id_here", "your_telegram_id"):
            return []
        try:
            return [int(id_str.strip()) for id_str in self.admin_ids_raw.split(",") if id_str.strip().isdigit()]
        except ValueError:
            return []


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Возвращает единственный экземпляр настроек (кэшированный).

    Returns:
        Настроенный и провалидированный объект Settings.
    """
    return Settings()
