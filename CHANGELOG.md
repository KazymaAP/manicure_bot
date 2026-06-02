# Changelog

All notable changes to this project will be documented in this file.

Format: [Semantic Versioning](https://semver.org/)

## [4.2.0] — 2026-06-02 (Fixed & Improved)

### Fixed — Баги исправлены
- **`AppointmentStatus.from_db_value()`** теперь корректно обрабатывает `None` (ранее падал с `TypeError`)
- **`Appointment.cancel()`** выбрасывает `ValueError` при повторной отмене уже отменённой записи
- **`Appointment.complete()`** — новый метод, запрещает завершение отменённой записи
- **`DomainError.__repr__()`** — добавлен для удобной отладки
- **`ValidationError`** — добавлен `field` атрибут для указания поля с ошибкой
- **`CreateBookingDTO`** — добавлены поля `created_at` и полная валидация `client_name`
- **`HealthServer._handle_not_found()`** — 404 для неизвестных путей
- **`HealthServer._check_metrics_auth()`** — `secrets.compare_digest` вместо `==` (защита от timing-атак)
- **`HealthServer`** — убрана утечка информации в 500-ответе `/metrics`
- **`AppointmentStatus.label`** — добавлено свойство для человекочитаемого статуса на русском

### Improved — Улучшения
- **Зависимости** — обновлены до актуальных безопасных версий (pydantic 2.10.4, aiohttp 3.11.11)
- **Тесты** — расширено покрытие: 50+ новых тест-кейсов
  - `TestAppointmentStatus` — тесты для label, boundary-значений `from_db_value`
  - `TestAppointmentModel` — тесты `complete()`, `cancel()` с guard'ами, `__eq__`, `__repr__`
  - `TestCreateBookingDTO` — полная валидация имени, телефона, комментария, граничных значений
  - `TestDatabaseManager` — тесты схемы (колонки, PRAGMA), конкурентности потоков, вложенных транзакций
  - `TestBackupService` — тесты ротации, содержимого бэкапа, авто-создания директории
  - `TestScheduleService` — тесты async-методов, шаблонов, граничных случаев дат
  - `TestSettings` — тесты SecretStr, часового пояса, кастомных слотов и услуг
  - `TestRateLimitMiddleware` — тесты `CallbackQuery`, `from_user=None`, `_MAX_BUCKETS`
- **`logging_config.py`** — расширенный формат (module:lineno), раздельные форматы для файла и консоли
- **`docker-compose.yml`** — добавлены `deploy.resources.limits` (CPU/RAM), `internal: false`
- **`.dockerignore`** — расширен (IDE файлы, распределённые артефакты сборки)
- **`.gitignore`** — расширен (WAL-файлы SQLite, htmlcov)
- **`pyproject.toml`** — добавлены `pytest-mock`, `branch=true` для coverage, `security` job в CI
- **`ci.yml`** — добавлен `security` job (pip-audit), `concurrency` группа

### Security
- `secrets.compare_digest` для сравнения токенов (timing-attack protection)
- Не возвращаем детали ошибок в HTTP 500 ответах
- Обновлены зависимости с исправленными CVE

## [4.1.0] — Предыдущая версия

Смотрите историю git для предыдущих изменений.
