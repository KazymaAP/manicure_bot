# Changelog

All notable changes to this project will be documented in this file.

Format: [Semantic Versioning](https://semver.org/)

## [4.4.0] — 2026-06-08 (Complete Audit Fix)

### Fixed — БЛОК 1: Критические баги

- **BUG 1.1** (`admin_handler.py`): Добавлены хендлеры `admin_slot_info` и `admin_toggle_slot`.
  Ранее нажатие на слот в разделе «Расписание» ничего не делало — хендлеры отсутствовали.
  `admin_slot_info` показывает статус слота (занят/свободен) и данные клиента если занят.
  `admin_toggle_slot` закрывает свободный слот через `sched_service.remove_slot()`.

- **BUG 1.2** (`admin_handler.py`): Добавлен отдельный хендлер `admin_photo_url_save`
  для состояния `waiting_for_photo_url`. Ранее URL фото сохранялся как текст рассылки
  и рассылался всем пользователям. Теперь URL валидируется (должен начинаться с `https://`)
  и сохраняется в `config.json["bot"]["welcome_photo_url"]`.

- **BUG 1.3** (`admin_handler.py`, `admin.py`): Разделена логика отмены на два шага.
  Кнопки «❌ Отменить» в разделах «Сегодня» и «Клиенты» теперь генерируют
  `callback_data="admin_cancel_request:{id}"` → новый хендлер показывает диалог подтверждения.
  Хендлер `admin_confirm_cancel` остаётся финальным шагом отмены.

- **BUG 1.4** (`Makefile`, `pyproject.toml`): Создан `Makefile` с целями `test`, `lint`,
  `format`, `run`. `make test` сначала устанавливает зависимости, потом запускает pytest.
  В `pyproject.toml` добавлен `filterwarnings` для подавления предупреждений pytest.

- **BUG 1.5** (`fsm_states.py`): Удалено мёртвое состояние `BookingFSM.transferring_confirming`
  — никогда не устанавливалось через `state.set_state()`. Подтверждение переноса
  выполняется inline в `transfer_confirm_new_slot`.

### Fixed — БЛОК 2: Дублирование кода

- **BUG 2.1** (`common_handler.py`, `user_handler.py`): Функция `_check_subscription`
  вынесена на уровень модуля как `check_subscription(user_id, bot, settings)`.
  В `user_handler.py` обе inline-проверки подписки заменены вызовами `check_subscription`.

- **BUG 2.2** (`admin_handler.py`, `config_writer.py`): Вложенная функция `_load_config()`
  заменена вызовом `_load_config_json` из `src/config/dependencies.py`.
  Создан `src/config/config_writer.py` с `save_config()` для переиспользования.

- **BUG 2.3** (`admin_handler.py`, `fsm_states.py`): Три отдельных хендлера вместо
  перегруженного `waiting_for_broadcast`: `waiting_for_welcome_text` → приветствие,
  `waiting_for_photo_url` → фото, `waiting_for_broadcast_text` → рассылка.

### Fixed — БЛОК 3: Безопасность и качество

- **BUG 3.1** (`fsm_states.py`): Удалены мёртвые FSM-состояния AdminFSM:
  `waiting_for_export_range`, `waiting_for_block_reason`, `confirming_cancel_all`,
  `waiting_for_unblock_user_id`, `BookingFSM.transferring_confirming`.
  Активные состояния `waiting_for_welcome_text`, `waiting_for_photo_url`,
  `waiting_for_broadcast_text` теперь используются.

- **BUG 3.2** (`admin_handler.py`): `settings.__dict__["reminder_hours_before"] = hours`
  заменён на `object.__setattr__(settings, "reminder_hours_before", hours)`.

- **BUG 3.3** (`admin_handler.py`): Все `import` перенесены в начало файла:
  `csv`, `io`, `tempfile`, `date`, `timedelta`, `InlineKeyboardButton`, `InlineKeyboardMarkup`.

- **BUG 3.4** (`admin_handler.py`, `schedule_service.py`, `appointment_service.py`):
  `except Exception: pass` заменены на `except Exception as exc: logger.debug/warning(...)`.

- **BUG 3.5** (`settings.py`): Добавлен `@field_validator("webhook_url")` который
  выводит `logger.warning` если `webhook_url` задан в .env (бот работает только в polling).

### Fixed — БЛОК 4: Недостающий функционал

- **BUG 4.1** (`main_menu.py`): Добавлены кнопки `📆 Расписание`, `🔔 Уведомления`
  и `📤 Поделиться` в главное меню клиента. Хендлеры уже существовали в
  `final_features_handler.py`, но кнопок не было.

- **BUG 4.2** (`admin_handler.py`): Добавлена проверка `_is_admin()` в начало
  хендлера `admin_client_history_cb`. Ранее любой пользователь мог вызвать
  состояние истории зная callback_data.

- **BUG 4.3** (`extended_features_handler.py`): Удалён дублирующий хендлер
  `admin_view_history` — мёртвый код без кнопки в интерфейсе.
  Корректный путь: `admin_client_history` → `admin_search_client_history`.

- **BUG 4.4** (`admin.py`): Добавлена кнопка `📋 Шаблоны расписания` в
  `AdminKeyboard.schedule_menu()`. Функционал шаблонов теперь доступен из меню расписания.

- **BUG 4.5** (`reminder_service.py`): В `_send_reminder_job` добавлен вызов
  `mark_reminder_sent(appointment_id)` после успешной отправки напоминания.

### Fixed — БЛОК 5: Упаковка и документация

- **BUG 5.1** (`.env.example`): Задокументированы все поля из `settings.py`:
  `WEBHOOK_URL`, `WEBHOOK_PORT`, `SCHEDULE_CHANNEL_ID`, `HEALTH_PORT`, `METRICS_TOKEN`
  и другие. У каждого поля пример значения и комментарий на русском.

- **BUG 5.2** (`.github/workflows/ci.yml`): Шаг установки зависимостей уже присутствует
  в CI. Проверено соответствие.

- **BUG 5.3** (`pyproject.toml`): Добавлен `filterwarnings` в `[tool.pytest.ini_options]`
  для подавления `PytestConfigWarning` и `PytestUnknownMarkWarning`.

### Added

- `Makefile` с целями: `make test`, `make lint`, `make format`, `make typecheck`, `make run`
- `src/config/config_writer.py` — вынесенная логика атомарного сохранения config.json

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
