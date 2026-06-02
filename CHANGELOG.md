# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [4.1.0] — 2026-06-02

### Added
- **Тесты**: 57 unit-тестов покрывают domain, services, infrastructure, middleware и config
  - `tests/unit/test_config/test_settings.py` — тесты Pydantic Settings
  - `tests/unit/test_domain/` — тесты моделей Appointment, AppointmentStatus, BookingDTO
  - `tests/unit/test_infrastructure/test_backup_service.py` — тесты BackupService
  - `tests/unit/test_infrastructure/test_database_manager.py` — тесты DatabaseManager
  - `tests/unit/test_middlewares/test_rate_limit.py` — тесты RateLimitMiddleware
  - `tests/unit/test_services/test_schedule_service.py` — тесты ScheduleService
- `tests/conftest.py` — общий `autouse` фикстур сброса DatabaseManager Singleton
- `pytest-cov==5.0.0` в зависимостях для измерения покрытия кода
- `[tool.pytest.ini_options]` в `pyproject.toml` — унифицированная конфигурация pytest
- `[tool.coverage.*]` секции в `pyproject.toml` для настройки coverage
- `.github/workflows/ci.yml` — полный CI pipeline (tests + mypy + ruff)
- `SECURITY.md` — политика безопасности
- `CHANGELOG.md` — история изменений
- Колонка `status` (INTEGER) в таблице `appointments` — корректное хранение статуса
- Миграция `004_add_appointment_status_column.sql`

### Fixed
- **`requirements.txt`**: удалён устаревший пакет `types-aiohttp==3.9.2` (несовместим с aiohttp 3.x, у которого есть встроенные стабы)
- **`backup_service.py`**: переход на `pathlib.Path` вместо смешанного использования `os.path` и `Path`; ротация использует `stat().st_mtime` (надёжнее сортировки по имени)
- **`logging_config.py`**: `RotatingFileHandler` вместо `FileHandler` — предотвращает бесконечный рост лог-файла; добавлен `datefmt` для читаемых временных меток
- **`appointment_service.py`**: `mark_completed()` использует колонку `status=2` (COMPLETED) вместо хака с `comment` — семантически правильное хранение состояния
- **`user_handler.py`**: `import re` перенесён на уровень модуля вместо импорта внутри функции
- **`tests/.../test_appointment_service.py`**: мок `is_user_blocked.return_value = False` — исправлен трудноуловимый баг где MagicMock() (truthy) вызывал ложную BlacklistedUserError
- **`.gitignore`**: добавлены паттерны `coverage.xml`, `data/backups/`, `*.jobstore.db`

### Changed
- `pyproject.toml`: версия проекта `4.0.0` → `4.1.0`
- `pyproject.toml`: `redis` extra обновлён, добавлен `aiogram[redis]`
- GitHub Actions: обновлены до `actions/checkout@v4`, `actions/setup-python@v5`
- `README.md`: обновлена документация — секции тестирования и схемы БД

## [4.0.0] — Initial Release

### Added
- Базовая функциональность бота для записи на маникюр
- Clean Architecture (Domain / Application / Infrastructure / Presentation)
- Административная панель с 6 разделами
- Система напоминаний через APScheduler
- SQLite БД с WAL режимом
- Docker / docker-compose поддержка
- Health check HTTP сервер
- Rate limiting middleware
- Waitlist (лист ожидания)
- Перенос записей клиентом
- Экспорт в CSV / архивирование
- Автоматический бэкап БД
