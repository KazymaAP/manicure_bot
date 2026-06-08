# Changelog

All notable changes to this project will be documented in this file.

Format: [Semantic Versioning](https://semver.org/)

## [4.3.0] — 2026-06-08 (Bug Fixes & Refactoring)

### Fixed — Критические баги исправлены

- **Баг #1** (`admin_handler.py`): Убран двойной вызов `callback.answer()` в `admin_edit_services` — второй вызов вызывал `TelegramBadRequest`
- **Баг #2** (`extended_features_handler.py`): `callback_data="admin_main_menu"` в кнопке подтверждения массовой отмены заменён на `admin_back_main` (рабочий хендлер)
- **Баг #3** (`admin_handler.py`, `schedule_service.py`): Реализовано применение шаблона расписания к дате — добавлен метод `apply_template_to_date` в `ScheduleService` и проверка `apply_template_id` в хендлере `admin_add_slot_date`
- **Баг #4** (`admin_handler.py`): Добавлен отдельный хендлер `admin_edit_photo_url` для FSM-состояния `waiting_for_photo_url` — URL фото приветствия теперь корректно сохраняется в config.json
- **Баг #5** (`admin_handler.py`, `extended_features_handler.py`): Удалён дублирующий хендлер `admin_client_history_search` в `admin_handler.py` — теперь используется только правильный SQL-поиск через `search_appointments_by_client` в `extended_features_handler.py`
- **Баг #6** (`extended_features_handler.py`): Удалён дублирующий хендлер `admin_cancel_all_execute` — оставлен только в `admin_handler.py`
- **Баг #7** (`admin_handler.py`): Заменён `get_appointments_filtered("all")` на `get_appointments_by_date(date_str)` в функциях `admin_cancel_all_date` и `admin_confirm_cancel_all` — устранена загрузка всех записей в память
- **Баг #8** (`extended_features_handler.py`): Удалены дублирующие `admin_cancel_all_start` и `admin_cancel_all_confirm` — оставлены рабочие версии в `admin_handler.py`

### Fixed — Дублирование кода

- **Баг #10** (`user_handler.py`): `import asyncio` вынесен на уровень модуля, удалены 8 локальных импортов внутри функций
- **Баг #11** (`extended_features_handler.py`): `import asyncio` вынесен на уровень модуля, удалены все локальные импорты
- **Баг #12** (`final_features_handler.py`): `import asyncio` вынесен на уровень модуля, удалены все локальные импорты
- **Баг #13** (`admin_handler.py`): `InlineKeyboardButton, InlineKeyboardMarkup` добавлены в общий импорт файла, удалены два локальных импорта внутри функций

### Fixed — Безопасность и качество

- **Баг #14** (`admin_handler.py`, `fsm_states.py`): FSM-конфликт устранён — добавлены три отдельных состояния: `waiting_for_welcome_text`, `waiting_for_photo_url`, `waiting_for_broadcast_text`; соответствующие хендлеры разделены
- **Баг #15** (`admin_handler.py`): Path traversal устранён — `config_path` в `admin_edit_welcome` нормализован через `os.path.normpath`
- **Баг #16** (`admin_handler.py`): Добавлена валидация URL фото: проверка `startswith("https://")` и отсутствия пробелов
- **Баг #17** (`final_features_handler.py`): После переключения уведомлений (24h/2h/1h) клавиатура теперь обновляется через `edit_reply_markup` — иконки 🔔/🔕 отображаются актуально

### Added — Новый функционал

- **Баг #18/3** (`schedule_service.py`): Метод `apply_template_to_date` добавлен в `ScheduleService` с корректной обработкой дублирования слотов
- **Баг #19** (`common_handler.py`): Добавлен хендлер-псевдоним `book_again_compat` для обратной совместимости со старым `callback_data="book_again"`
- **Баг #20** (`reminder_service.py`): Параметр `hrs` добавлен в `_send_reminder_job`; теперь проверяются отдельные флаги `notif_24h`, `notif_2h`, `notif_1h` перед отправкой

### Infrastructure

- **Баг #24**: Добавлена миграция `006_add_appointments_date_index.sql` — составной индекс `(date, is_cancelled)` и `(user_id, is_cancelled)` для таблицы `appointments`

---

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
