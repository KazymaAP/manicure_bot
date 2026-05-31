# 💅 Manicure Bot — Подробная документация

> **Telegram-бот для онлайн-записи клиентов к мастеру маникюра.**  
> Версия: **4.0.0** · Python **3.10+** · aiogram **3.13.1** · SQLite · Docker-ready

---

## Содержание

1. [Что это за проект и зачем он нужен](#1-что-это-за-проект-и-зачем-он-нужен)
2. [Архитектура и слои приложения](#2-архитектура-и-слои-приложения)
3. [Структура проекта — каждый файл](#3-структура-проекта--каждый-файл)
4. [База данных — таблицы и схема](#4-база-данных--таблицы-и-схема)
5. [Функциональность для клиентов](#5-функциональность-для-клиентов)
6. [Функциональность для администратора](#6-функциональность-для-администратора)
7. [Все кнопки и команды](#7-все-кнопки-и-команды)
8. [FSM — сценарии диалогов](#8-fsm--сценарии-диалогов)
9. [Планировщик задач (APScheduler)](#9-планировщик-задач-apscheduler)
10. [Уведомления](#10-уведомления)
11. [Быстрый старт — установка и запуск](#11-быстрый-старт--установка-и-запуск)
12. [Настройка конфигурации (.env)](#12-настройка-конфигурации-env)
13. [Настройка внешнего вида (config.json)](#13-настройка-внешнего-вида-configjson)
14. [Docker-деплой](#14-docker-деплой)
15. [Тесты и CI](#15-тесты-и-ci)
16. [Зависимости и технологический стек](#16-зависимости-и-технологический-стек)

---

## 1. Что это за проект и зачем он нужен

**Manicure Bot** — это полностью готовый Telegram-бот для автоматизации онлайн-записи клиентов к мастеру маникюра (или другому бьюти-специалисту). Клиент может самостоятельно, без звонков и переписки, выбрать услугу, дату и время, ввести своё имя и телефон, и подтвердить запись. Мастер (администратор) моментально получает уведомление, управляет расписанием через удобный интерфейс в самом боте и никогда не пропустит новую запись.

### Для кого

| Роль | Что получает |
|---|---|
| **Клиент** | Удобная онлайн-запись в любое время, автоматические напоминания, возможность перенести или отменить запись |
| **Мастер/Администратор** | Полный контроль расписания, мгновенные уведомления, статистика, рассылка, экспорт CSV, чёрный список |
| **Разработчик** | Чистая архитектура (Domain/Application/Infrastructure/Presentation), DI-контейнер, строгая типизация mypy, unit-тесты |

---

## 2. Архитектура и слои приложения

Проект построен по принципам **Clean Architecture** (чистой архитектуры) с разделением на четыре слоя. Каждый слой зависит только от более внутренних слоёв — никакого «спагетти»-кода.

```
┌──────────────────────────────────────────────┐
│           PRESENTATION LAYER                 │  ← Telegram-обработчики,
│  handlers / keyboards / middlewares /        │    клавиатуры, форматтеры
│  formatters                                  │
├──────────────────────────────────────────────┤
│           APPLICATION LAYER                  │  ← Бизнес-логика:
│  services / dto / use_cases                  │    создание записей, уведомления,
│                                              │    расписание, напоминания, бэкап
├──────────────────────────────────────────────┤
│           DOMAIN LAYER                       │  ← Доменные модели, исключения,
│  models / enums / exceptions                 │    перечисления статусов
├──────────────────────────────────────────────┤
│           INFRASTRUCTURE LAYER               │  ← БД (SQLite), репозитории,
│  database / repositories / http              │    HTTP health-check сервер
└──────────────────────────────────────────────┘
```

**DI-контейнер (Container)** в `src/config/dependencies.py` — это центральная точка сборки: он создаёт все репозитории, сервисы и связывает их друг с другом. Хендлеры получают готовые объекты через фабричные функции `setup_*_router(container)`.

---

## 3. Структура проекта — каждый файл

```
manicure_bot/
├── main.py                          # Точка входа бота
├── config.json                      # Тексты, кнопки, расписание (кастомизация UI)
├── .env.example                     # Шаблон переменных окружения
├── requirements.txt                 # Зависимости Python
├── pyproject.toml                   # Метаданные, ruff, mypy
├── Dockerfile                       # Multi-stage Docker образ
├── docker-compose.yml               # Docker Compose для продакшн
├── .dockerignore                    # Исключения для Docker
├── .gitignore                       # Исключения для git
├── requirements_instructions.txt   # Расширенные инструкции/техзадание
│
├── .github/
│   └── workflows/
│       └── mypy.yml                 # CI: проверка типов mypy --strict
│
├── migrations/
│   └── 001_initial.sql              # SQL-миграция: создание всех таблиц БД
│
├── src/
│   ├── __init__.py
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py              # Pydantic-настройки из .env (все параметры)
│   │   ├── dependencies.py          # DI-контейнер — сборка всех сервисов
│   │   └── logging_config.py        # Настройка логирования (stdout + файл)
│   │
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── appointment.py       # Доменная модель «Запись клиента»
│   │   │   ├── working_day.py       # Доменная модель «Рабочий день»
│   │   │   └── time_slot.py         # Доменная модель «Временной слот»
│   │   ├── enums/
│   │   │   ├── __init__.py
│   │   │   ├── appointment_status.py # Статусы записи: ACTIVE=0, CANCELLED=1
│   │   │   ├── day_status.py         # Статусы дня: OPEN=0, CLOSED=1
│   │   │   └── fsm_states.py         # FSM-состояния для BookingFSM и AdminFSM
│   │   └── exceptions/
│   │       ├── __init__.py
│   │       ├── base.py              # Базовые исключения: DomainError, ValidationError
│   │       ├── appointment.py       # Исключения записей (SlotAlreadyBooked, MaxReached…)
│   │       └── schedule.py          # Исключения расписания (PastDate, DayNotFound…)
│   │
│   ├── application/
│   │   ├── __init__.py
│   │   ├── dto/
│   │   │   ├── __init__.py
│   │   │   └── booking_dto.py       # DTO: CreateBookingDTO, BookingResultDTO, AddSlotDTO…
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── appointment_service.py  # Сервис записей: создание, отмена, поиск
│   │   │   ├── schedule_service.py     # Сервис расписания: дни, слоты, шаблоны
│   │   │   ├── notification_service.py # Сервис уведомлений: клиент, admin, канал
│   │   │   ├── reminder_service.py     # Сервис напоминаний + планировщик APScheduler
│   │   │   └── backup_service.py       # Сервис резервного копирования SQLite
│   │   └── use_cases/
│   │       └── __init__.py          # Зарезервировано для use cases (пусто)
│   │
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   ├── database/
│   │   │   ├── __init__.py
│   │   │   └── connection.py        # DatabaseManager: Singleton, WAL, транзакции
│   │   ├── repositories/
│   │   │   ├── __init__.py
│   │   │   ├── base.py              # BaseRepository: общий конструктор
│   │   │   ├── appointment_repository.py  # SQL-операции с таблицей appointments
│   │   │   └── schedule_repository.py     # SQL-операции с working_days + time_slots
│   │   └── http/
│   │       ├── __init__.py
│   │       └── health_server.py     # HTTP-сервер: /health и /metrics (aiohttp)
│   │
│   └── presentation/
│       ├── __init__.py
│       ├── constants.py             # Русские названия месяцев, дней недели
│       ├── formatters/
│       │   ├── __init__.py
│       │   └── message_formatter.py # Все тексты сообщений (читает из config.json)
│       ├── handlers/
│       │   ├── __init__.py
│       │   ├── common_handler.py         # /start, /help, /cancel, 🏠 Главное меню
│       │   ├── user_handler.py           # Запись клиента: FSM-сценарий полностью
│       │   ├── admin_handler.py          # Панель администратора: все команды
│       │   ├── extended_features_handler.py  # Перенос записей, лист ожидания, история
│       │   └── final_features_handler.py     # /mybookings, /slots, /schedule, inline
│       ├── keyboards/
│       │   ├── __init__.py
│       │   ├── main_menu.py         # ReplyKeyboard: главное меню клиента
│       │   ├── booking.py           # InlineKeyboard: запись, выбор услуги/времени
│       │   ├── calendar.py          # InlineKeyboard: встроенный календарь
│       │   └── admin.py             # ReplyKeyboard + InlineKeyboard: панель админа
│       └── middlewares/
│           ├── __init__.py
│           ├── logging_middleware.py    # Логирование + трекинг пользователей в БД
│           └── rate_limit_middleware.py # Rate-limit: 5 запросов за 5 секунд на юзера
│
└── tests/
    ├── __init__.py
    └── unit/
        ├── __init__.py
        ├── test_repositories/
        │   └── __init__.py          # Зарезервировано (пусто)
        └── test_services/
            ├── __init__.py
            └── test_appointment_service.py  # Unit-тесты AppointmentService
```

---

### Детальное описание каждого файла

---

#### `main.py` — Точка входа

Главный файл запуска бота. Выполняет по порядку:

1. Загружает настройки через `get_settings()` (Pydantic из `.env`)
2. Настраивает логирование (`setup_logging`)
3. Инициализирует хранилище FSM — **Redis** (если `REDIS_URL` задан) или **MemoryStorage**
4. Создаёт объект `Bot` (с `ParseMode.HTML` по умолчанию) и `Dispatcher`
5. Создаёт и инициализирует **DI-контейнер** (`Container`) — БД и все сервисы
6. Регистрирует **middleware**: `LoggingMiddleware` и `RateLimitMiddleware`
7. Подключает **5 роутеров**: common, user, admin, extended_features, final_features
8. Запускает **планировщик напоминаний** и восстанавливает задачи из БД
9. Планирует 4 cron-задачи: ежедневный дайджест (9:00 UTC), ежедневный бэкап (2:00 UTC), еженедельный архив (вс 3:00 UTC), проверка слотов (10:00 UTC)
10. Запускает **HTTP health-check сервер** на порту `HEALTH_PORT` (по умолчанию 8080)
11. Запускает **polling** (`dp.start_polling`)
12. При остановке корректно завершает все сервисы (`graceful shutdown`)

---

#### `config.json` — Настройка внешнего вида

JSON-файл для кастомизации бота **без изменения кода**. Читается один раз при старте и кэшируется. Содержит:

- **`bot`** — название, название услуги, имя мастера, приветственный эмодзи
- **`messages`** — тексты всех сообщений: приветствие, справка, успешная запись, ошибки, подсказки
- **`notifications`** — шаблоны уведомлений администратору и клиенту (с плейсхолдерами `{client_name}`, `{date}`, `{time}`, `{phone}`, `{id}`, `{username}`)
- **`buttons`** — надписи всех кнопок главного меню
- **`schedule`** — горизонт расписания (`days_ahead = 30`) и временные слоты по умолчанию (`09:00`–`18:00`)

> Если ключ из `config.json` не найден, используется встроенный дефолт из `MessageFormatter`.

---

#### `src/config/settings.py` — Конфигурация через Pydantic

Класс `Settings` (наследует `BaseSettings`) загружает **все параметры** из файла `.env` или переменных окружения с автоматической валидацией.

| Параметр | Тип | Описание |
|---|---|---|
| `BOT_TOKEN` | `str` | ⚠️ Обязательный. Токен от @BotFather |
| `ADMIN_IDS` | `str` | Telegram ID администраторов через запятую |
| `DB_PATH` | `str` | Путь к файлу SQLite (по умолч. `data/manicure_bot.db`) |
| `REMINDER_HOURS_BEFORE` | `int` | За сколько часов отправлять напоминание (по умолч. `24`) |
| `MAX_APPOINTMENTS_PER_USER` | `int` | Макс. активных записей на 1 клиента (по умолч. `1`) |
| `REQUIRED_CHANNEL` | `str\|None` | @username канала для обязательной подписки |
| `SCHEDULE_CHANNEL_ID` | `int` | ID канала для публикации новых записей (-1 = выкл.) |
| `PORTFOLIO_URL` | `str\|None` | Ссылка на портфолио (Instagram, сайт) |
| `REDIS_URL` | `str\|None` | Redis для хранения FSM состояний |
| `LOG_LEVEL` | `str` | Уровень логов: DEBUG / INFO / WARNING / ERROR |
| `LOG_FILE` | `str\|None` | Путь к файлу логов (`bot.log`) |
| `TIMEZONE` | `str` | Временная зона напоминаний (`Europe/Moscow`) |
| `HEALTH_PORT` | `int` | Порт HTTP health-check сервера (по умолч. `8080`) |
| `WELCOME_PHOTO_URL` | `str\|None` | URL фото для приветственного баннера |
| `PHONE` | `str\|None` | Телефон мастера для команды `/contacts` |
| `INSTAGRAM` | `str\|None` | Instagram мастера |
| `ADDRESS` | `str\|None` | Адрес студии |
| `MAPS_LINK` | `str\|None` | Ссылка на карту |
| `SERVICES` | `dict` | Услуги с ценой и длительностью в JSON |
| `WORK_DAYS` | `list[int]` | Рабочие дни недели 1=Пн…7=Вс (по умолч. 1-5) |

Функция `get_settings()` кэширует объект Settings через `@lru_cache(maxsize=1)` — настройки читаются из `.env` только один раз.

---

#### `src/config/dependencies.py` — DI-контейнер

Класс `Container` управляет жизненным циклом всех объектов приложения:

- **`initialize()`** — создаёт `DatabaseManager` и инициализирует схему таблиц
- **`build_services(bot)`** — создаёт все репозитории и сервисы в правильном порядке зависимостей:
  1. `AppointmentRepository` + `ScheduleRepository`
  2. `ScheduleService`
  3. `NotificationService`
  4. `AppointmentService` (с callback для waitlist-уведомлений)
  5. `BackupService`
  6. `ReminderService`
- **`shutdown()`** — async-метод для корректного закрытия БД

Также загружает `config.json` через `_load_config_json()` (кэшированный) для получения названия услуги.

---

#### `src/config/logging_config.py` — Логирование

Функция `setup_logging(log_level, log_file)`:
- Очищает существующие хендлеры (предотвращает дублирование при повторном вызове)
- Добавляет хендлер `stdout` с форматом `%(asctime)s [%(levelname)s] %(name)s: %(message)s`
- Опционально добавляет файловый хендлер (если `log_file` задан)
- Подавляет избыточные логи aiogram, aiohttp, apscheduler до уровня WARNING

---

#### `src/domain/models/appointment.py` — Модель «Запись»

Датакласс `Appointment` (`slots=True`) — доменная сущность записи клиента:

| Поле | Тип | Описание |
|---|---|---|
| `user_id` | `int` | Telegram ID клиента |
| `client_name` | `str` | Имя клиента |
| `phone` | `str` | Телефон клиента |
| `date` | `str` | Дата «YYYY-MM-DD» |
| `time` | `str` | Время «HH:MM» |
| `id` | `int\|None` | ID в базе данных (None до сохранения) |
| `username` | `str\|None` | Telegram username |
| `created_at` | `datetime\|None` | Дата создания записи |
| `reminder_sent` | `bool` | Отправлено ли напоминание |
| `status` | `AppointmentStatus` | ACTIVE или CANCELLED |
| `comment` | `str\|None` | Комментарий клиента |
| `service` | `str\|None` | Выбранная услуга |

**Методы:** `cancel()`, `mark_reminder_sent()`, `from_row(dict)`, `to_dict()`, свойства `is_active`, `is_cancelled`, `datetime`.

---

#### `src/domain/models/working_day.py` — Модель «Рабочий день»

`WorkingDay` — рабочий день мастера с полями `date`, `id`, `status` (`DayStatus.OPEN/CLOSED`). Методы: `close()`, `open()`, `from_row()`, `to_dict()`, свойства `is_open`, `is_closed`.

---

#### `src/domain/models/time_slot.py` — Модель «Временной слот»

`TimeSlot` — конкретный временной слот с полями `date`, `time`, `id`, `is_booked`. Методы: `book()`, `release()`, `from_row()`, `to_dict()`, свойство `is_free`.

---

#### `src/domain/enums/fsm_states.py` — FSM состояния

Определяет все состояния конечного автомата (FSM) для управления диалогами:

**`BookingFSM`** (запись клиента):
- `choosing_service` — выбор услуги
- `choosing_date` — выбор даты в календаре
- `choosing_time` — выбор времени
- `entering_name` — ввод имени
- `entering_phone` — ввод телефона
- `entering_comment` — ввод комментария (опционально)
- `confirming` — подтверждение записи
- `transferring_choosing_date` — выбор новой даты при переносе
- `transferring_choosing_time` — выбор нового времени при переносе
- `transferring_confirming` — подтверждение переноса

**`AdminFSM`** (панель администратора):
- `waiting_for_appointment_id` — ожидание ID для отмены
- `confirming_cancel` — подтверждение отмены
- `waiting_for_date` / `waiting_for_time` — добавление слота
- `waiting_for_broadcast` — ввод текста рассылки
- `waiting_for_export_range` — диапазон дат для CSV
- `waiting_for_blacklist_id` / `waiting_for_block_reason` — блокировка пользователя
- `waiting_for_unblock_user_id` — разблокировка
- `waiting_for_search_query` — поиск клиента
- `confirming_cancel_all` / `confirming_cancel_all_date` — массовая отмена
- `waiting_for_template_name` / `waiting_for_template_schedule` — шаблоны

---

#### `src/domain/exceptions/` — Исключения

- **`base.py`**: `DomainError` (базовое), `ValidationError`
- **`appointment.py`**:
  - `AppointmentNotFoundError` — запись не найдена
  - `AppointmentAlreadyExistsError` — пользователь уже записан
  - `SlotAlreadyBookedError` — слот уже занят
  - `MaxAppointmentsReachedError` — превышен лимит записей
  - `BlacklistedUserError` — пользователь в чёрном списке
- **`schedule.py`**:
  - `WorkingDayAlreadyExistsError` — день уже существует
  - `WorkingDayNotFoundError` — день не найден
  - `PastDateError` — попытка добавить прошедшую дату
  - `SlotNotFoundError` — слот не найден

---

#### `src/application/dto/booking_dto.py` — Data Transfer Objects

Неизменяемые (`frozen=True`) датаклассы для передачи данных между слоями:

- **`CreateBookingDTO`** — данные для создания записи (user_id, имя, телефон, дата, время, комментарий, услуга). Содержит валидацию форматов даты (YYYY-MM-DD) и времени (HH:MM) в `__post_init__`.
- **`BookingResultDTO`** — результат создания (appointment_id, имя, дата, время)
- **`AddWorkingDayDTO`** — данные для добавления рабочего дня
- **`AddSlotDTO`** — данные для добавления слота (дата + время)

---

#### `src/application/services/appointment_service.py` — Сервис записей

Центральный сервис бизнес-логики по работе с записями клиентов.

**Ключевые методы:**

| Метод | Описание |
|---|---|
| `create_booking(dto)` | Атомарное создание записи в транзакции `BEGIN IMMEDIATE`: проверка лимита → чёрный список → бронирование слота → вставка записи |
| `cancel_by_user(user_id)` | Отмена записи самим клиентом |
| `cancel_by_id(appt_id)` | Отмена по ID (с проверкой существования) |
| `admin_cancel_appointment(appt_id)` | Отмена администратором (без проверки владельца) |
| `get_user_appointments(user_id)` | Все активные записи пользователя |
| `get_appointments_filtered(filter_key)` | Фильтр для admin: today / week / active / all |
| `search_appointments_by_client(query)` | Поиск по имени или телефону |
| `get_statistics()` | Статистика: total, confirmed, cancelled, today, week |
| `get_last_appointment(user_id)` | Последняя запись для персонализации |
| `get_client_visit_history(user_id)` | История посещений клиента |
| `get_month_statistics(year, month)` | Статистика по месяцам |
| `block_user(user_id, reason)` | Добавить в чёрный список |
| `unblock_user(user_id)` | Удалить из чёрного списка |
| `is_user_blocked(user_id)` | Проверка чёрного списка |

При отмене записи — автоматически уведомляет пользователей из waitlist через `notification_callback`.

---

#### `src/application/services/schedule_service.py` — Сервис расписания

Управляет рабочими днями и временными слотами мастера.

**Ключевые методы:**

| Метод | Описание |
|---|---|
| `add_working_day(dto)` | Добавить рабочий день с дефолтными слотами |
| `get_available_dates(from_date, days_ahead)` | Множество дат со свободными слотами |
| `get_available_dates_async()` | Async-обёртка для get_available_dates |
| `get_free_slots(date_str)` | Список свободных слотов на дату |
| `get_available_slots(date_str)` | Async-обёртка для get_free_slots |
| `open_day(date_str)` | Открыть рабочий день |
| `close_day(date_str)` | Закрыть рабочий день |
| `toggle_working_day(date_str)` | Переключить статус дня |
| `add_slot(date_str, time_str)` | Добавить временной слот |
| `remove_slot(date_str, time_str)` | Удалить слот |
| `get_nearest_free_slots(limit)` | Ближайшие N свободных слотов |
| `get_nearest_slots_async(limit)` | Async-обёртка |
| `join_waitlist(user_id, date)` | Добавить в лист ожидания |
| `get_workday_templates()` | Список шаблонов расписания |
| `save_workday_template(name, schedule)` | Сохранить шаблон |

---

#### `src/application/services/notification_service.py` — Сервис уведомлений

Централизует логику отправки всех Telegram-сообщений.

| Метод | Кому | Когда |
|---|---|---|
| `notify_admin_new_booking(appt_id)` | Всем админам | При новой записи |
| `notify_admins_list(text)` | Всем админам | Произвольный текст |
| `notify_channel_new_booking(appt_id)` | Канал расписания | При новой записи |
| `notify_admin_cancellation(appt_id)` | Всем админам | Клиент отменил |
| `notify_client_booking_confirmed(user_id, date, time)` | Клиенту | Подтверждение |
| `notify_client_cancellation_by_admin(user_id, date, time)` | Клиенту | Админ отменил |
| `send_reminder(user_id, time, appt_id)` | Клиенту | Напоминание с кнопками ✅/❌ |
| `notify_waitlist_slot_available(user_id, date, time)` | Клиенту из waitlist | Освободился слот |

Метод `_safe_send` перехватывает ошибки Telegram API (бот заблокирован, пользователь деактивирован) и не крашит приложение.

---

#### `src/application/services/reminder_service.py` — Сервис напоминаний

Управляет планировщиком APScheduler и всеми периодическими задачами.

**Напоминания о записях:**
- При создании записи планируются напоминания за **24 часа**, **2 часа** и **1 час** до визита
- При отмене — все напоминания удаляются
- При перезапуске бота — напоминания восстанавливаются из БД (`restore_reminders`)
- Задачи персистентно хранятся в SQLite через `SQLAlchemyJobStore`
- Поддерживает timezone-aware расчёт времени (параметр `TIMEZONE`)

**Cron-задачи:**

| Задача | Время | Описание |
|---|---|---|
| `schedule_daily_digest` | 9:00 UTC каждый день | Утренняя сводка администратору |
| `schedule_daily_backup` | 2:00 UTC каждый день | Резервная копия БД |
| `schedule_weekly_archive` | 3:00 UTC каждое вс | Архивирование старых записей |
| `schedule_insufficient_slots_check` | 10:00 UTC каждый день | Уведомление если < 3 дней |

---

#### `src/application/services/backup_service.py` — Сервис бэкапа

`BackupService` создаёт резервные копии файла SQLite с помощью встроенного **`sqlite3.backup()` API** (корректно работает при включённом WAL-режиме).

- Файлы сохраняются в `data/backups/backup_YYYYMMDD_HHMMSS_manicure_bot.db`
- Автоматическая **ротация**: хранится только `keep_count=7` последних файлов
- Старые бэкапы удаляются автоматически

---

#### `src/infrastructure/database/connection.py` — DatabaseManager

**Потокобезопасный Singleton** для управления соединениями SQLite:

- WAL-режим (`journal_mode=WAL`) для параллельного чтения
- `check_same_thread=False`, thread-local соединения — каждый поток имеет своё соединение
- Контекстный менеджер `transaction()` — автоматический коммит/роллбэк
- Контекстный менеджер `read_connection()` — для READ-only операций
- При инициализации создаёт директорию для БД и проверяет права на запись
- PRAGMA настройки: `foreign_keys=ON`, `synchronous=NORMAL`, `cache_size=-8000`, `temp_store=MEMORY`

---

#### `src/infrastructure/repositories/appointment_repository.py` — Репозиторий записей

Все SQL-запросы к таблице `appointments`:

- `create(appointment)` — INSERT новой записи
- `get_by_id(id)` — SELECT по ID
- `get_active_by_user_id(user_id)` — активная запись пользователя
- `get_active_list_by_user_id(user_id)` — все активные записи пользователя
- `get_by_date(date)` — все записи на дату
- `get_by_date_range(from, to)` — записи в диапазоне дат
- `get_all_active()` — все активные записи
- `get_all()` — все записи (включая отменённые)
- `cancel(id)` — отмена: `SET is_cancelled=1`
- `mark_reminder_sent(id)` — `SET reminder_sent=1`
- `get_upcoming_unreminded()` — предстоящие без напоминания
- `search_by_client(query)` — LIKE-поиск по имени и телефону
- `get_statistics_raw()` — эффективный COUNT-запрос для статистики
- `get_client_history(user_id)` — история посещений
- `get_month_statistics(year, month)` — статистика по месяцу
- `block_user(user_id, reason)` — INSERT в blacklist
- `unblock_user(user_id)` — DELETE из blacklist
- `is_user_blocked(user_id)` — SELECT из blacklist

---

#### `src/infrastructure/repositories/schedule_repository.py` — Репозиторий расписания

Все SQL-запросы к таблицам `working_days`, `time_slots`, `waitlist`, `workday_templates`:

- `add_working_day(date, slots)` — INSERT рабочего дня + слотов
- `get_working_day(date)` — SELECT по дате
- `get_available_dates_in_range(from, to)` — оптимизированный запрос доступных дат (без N+1)
- `get_free_slots(date)` — свободные слоты
- `get_all_slots(date)` — все слоты (включая занятые)
- `book_slot(date, time)` — `SET is_booked=1`
- `book_slots_with_conn(conn, date, time, duration)` — атомарное бронирование с учётом длительности
- `release_slot(date, time)` — освобождение слота + возврат waitlist для уведомлений
- `set_day_status(date, is_closed)` — открыть/закрыть день
- `add_time_slot(date, time)` — добавить слот
- `delete_time_slot(date, time)` — удалить свободный слот
- `join_waitlist(user_id, date)` — добавить в лист ожидания
- `get_workday_templates()` / `save_workday_template(name, slots)` — шаблоны

---

#### `src/infrastructure/http/health_server.py` — Health-check сервер

Лёгкий **aiohttp** HTTP-сервер для мониторинга:

- **`GET /health`** — `{"status": "ok", "timestamp": ..., "uptime_seconds": ...}`
- **`GET /metrics`** — статистика бота: total/active/cancelled/today/week записей

Используется Docker Compose healthcheck (`curl -f http://localhost:8080/health`), Uptime Robot, Grafana.

---

#### `src/presentation/handlers/common_handler.py` — Общие обработчики

| Триггер | Действие |
|---|---|
| `/start` | Приветствие с персонализацией (имя из последней записи), проверка подписки, фото-баннер если задан `WELCOME_PHOTO_URL` |
| `/help` | Справочное сообщение |
| `/cancel` | Сброс FSM-состояния, возврат в главное меню |
| `🏠 Главное меню` | Показ главного меню |
| `callback: check_subscription` | Повторная проверка подписки после нажатия «Я подписался» |

Функция `_check_subscription()` — проверяет подписку на обязательный канал. Администраторы обходят проверку. При ошибке API — не блокирует пользователя (fail-open).

---

#### `src/presentation/handlers/user_handler.py` — Обработчики клиента

Реализует полный FSM-сценарий записи:

| Триггер | FSM-состояние | Действие |
|---|---|---|
| `📅 Записаться` | → `choosing_service` | Очищает FSM, проверяет подписку, показывает выбор услуги |
| `callback: service:*` | `choosing_service` | Сохраняет услугу, показывает календарь |
| `callback: use_prev` | любое | Автозаполнение из последней записи |
| `callback: cal_prev/next:*` | `choosing_date` | Навигация по месяцам в календаре |
| `callback: cal_day:*` | `choosing_date` | Выбор даты → список слотов или предложение встать в waitlist |
| `callback: slot:*` | `choosing_time` | Выбор времени → ввод имени (или комментарий если данные есть) |
| Текст | `entering_name` | Валидация имени (2–100 символов) |
| Текст | `entering_phone` | Валидация телефона (7–15 цифр, E.164) |
| Текст/callback skip | `entering_comment` | Ввод или пропуск комментария |
| `callback: booking_confirm` | `confirming` | Атомарное создание записи, уведомление admin, планирование напоминания |
| `callback: booking_cancel` | `confirming` | Отмена без сохранения |
| `📋 Мои записи` | — | Список активных записей с кнопками отмены и переноса |
| `callback: cancel_appt:*` | — | Отмена конкретной записи + уведомление admin |
| `callback: reminder_yes:*` | — | Подтверждение прихода из напоминания |
| `callback: reminder_no:*` | — | Отмена записи из напоминания |
| `🟢 Ближайшие слоты` | — | Список 5 ближайших свободных слотов |

---

#### `src/presentation/handlers/admin_handler.py` — Обработчики администратора

| Триггер | Действие |
|---|---|
| `/admin` или `⚙️ Админ-панель` | Дашборд со статистикой дня + меню |
| `📋 Все записи` | Фильтр записей (сегодня/неделя/активные/все) |
| `❌ Отменить запись` | Ввод ID → подтверждение → отмена + уведомление клиента |
| `📅 Расписание` | Список рабочих дней с inline-управлением слотами |
| `➕ Добавить слот` | Ввод даты и времени → добавление слота |
| `🗓 Открыть день` / `🔒 Закрыть день` | Ввод даты → открыть/закрыть день |
| `📊 Статистика` | Сводная статистика: total/confirmed/cancelled/today/week |
| `📢 Рассылка` | Ввод текста → предпросмотр → отправка всем пользователям из таблицы users |
| `⬇️ Экспорт CSV` | Ввод диапазона дат → CSV-файл в чат |
| `📅 Открыть неделю` | Открыть 7 рабочих дней вперёд (учитывает `WORK_DAYS`) |
| `🔍 Найти клиента` | Поиск по имени/телефону |
| `🛑 Черный список` | Меню: заблокировать / разблокировать пользователя |
| `🚫 Отменить все записи на дату` | Массовая отмена с уведомлением каждого клиента |

---

#### `src/presentation/handlers/extended_features_handler.py` — Расширенные функции

| Функция | Триггер | Описание |
|---|---|---|
| **Перенос записи** | `callback: transfer_appt:*` | FSM-сценарий: выбор новой даты и времени, сначала отмена старой → создание новой |
| **Лист ожидания** | `callback: join_waitlist:*` | Добавление в waitlist на конкретную дату (при освобождении слота — автоуведомление) |
| **История клиента (admin)** | `callback: admin_view_history` | Поиск клиента по имени/телефону → полная история посещений |
| **Статистика по месяцам (admin)** | `callback: admin_monthly_stats` | Статистика за текущий месяц: лучшие дни недели, пиковые часы |
| **Шаблоны расписания (admin)** | `callback: admin_templates` | Сохранение и применение шаблонов рабочих дней |
| **Массовая отмена** | `callback: confirm_cancel_all:*` | Подтверждённая массовая отмена всех записей на дату |

---

#### `src/presentation/handlers/final_features_handler.py` — Финальные функции

| Команда/кнопка | Описание |
|---|---|
| `/mybookings` | Быстрый доступ к записям (аналог `📋 Мои записи`) |
| `/slots` | 5 ближайших свободных слотов с мини-календарём |
| `📆 Расписание` | Расписание с количеством свободных мест на каждую дату |
| `📞 Контакты` | Телефон, Instagram, адрес, ссылка на карту |
| `💰 Цены` | Список услуг из `SERVICES` с ценами |
| `📤 Поделиться` | Ссылка на бота для пересылки |
| `🔔 Уведомления` | Настройки уведомлений (включить/выключить) |
| Inline-режим | Поиск свободных дат через `@botname query` |

---

#### `src/presentation/keyboards/` — Клавиатуры

**`main_menu.py` (MainMenuKeyboard):**
- `main(is_admin, portfolio_url)` — ReplyKeyboard главного меню клиента (8 кнопок + опционально «Портфолио» + «Админ-панель»)
- `subscribe(channel_link)` — InlineKeyboard с кнопками «📢 Подписаться» и «✅ Я подписался»
- `back_to_main()` — кнопка «🏠 Главное меню»

**`booking.py` (BookingKeyboard):**
- `time_slots(date, slots)` — кнопки времени (3 в ряд) + «⬅️ Назад»
- `service_selection(services)` — динамические кнопки услуг из настроек или дефолтные (Маникюр/Педикюр/Покрытие)
- `use_previous_data()` — кнопка «Использовать прошлые данные»
- `time_selection(times)` — кнопки времени для переноса записи
- `confirm()` — «✅ Подтвердить» / «❌ Отмена»
- `skip_comment()` — «➡️ Пропустить»
- `cancel_appointment(appt_id)` — «❌ Отменить запись» + «⬅️ Главное меню»
- `cancel_appointment_list(appointments)` — для каждой записи: «❌ дата время» и «🔄 Перенести»

**`calendar.py` (CalendarKeyboard):**
- `build(year, month, available_dates, prefix)` — полный inline-календарь с навигацией по месяцам
- Доступные даты: `✅N` (кликабельны), прошедшие: `✖️N` (неактивны), остальные — серые цифры
- Поддерживает кастомный `prefix` для разграничения обычного бронирования и переноса

**`admin.py` (AdminKeyboard):**
- `main_menu()` — ReplyKeyboard администратора (14 кнопок: все записи, расписание, слоты, статистика, рассылка, CSV, черный список и др.)
- `appointments_filter()` — 4 фильтра: сегодня/неделя/активные/все
- `confirm_cancel(appt_id)` — подтверждение отмены записи
- `schedule_dates(dates)` — список рабочих дней для управления
- `day_slots(date, slots)` — список слотов с кнопками удаления
- `confirm_delete_slot(date, time)` — подтверждение удаления слота
- `toggle_day(date, is_working)` — открыть/закрыть день
- `blacklist_menu()` — заблокировать/разблокировать
- `broadcast_confirm(text)` — подтверждение рассылки
- `cancel_all_confirm(date, count)` — подтверждение массовой отмены
- `templates_menu()` — управление шаблонами расписания

---

#### `src/presentation/middlewares/logging_middleware.py` — Middleware логирования

Выполняется для каждого входящего сообщения и callback:
1. Определяет `user_id` и тип апдейта (`message` / `callback_query`)
2. **Трекинг пользователя**: INSERT/UPDATE в таблицу `users` (id, username, имя, last_seen) — используется для полноценной рассылки всем кто когда-либо писал боту
3. Вызывает следующий хендлер
4. Логирует время выполнения в миллисекундах

---

#### `src/presentation/middlewares/rate_limit_middleware.py` — Rate-limit

Защита от флуда: **5 запросов за 5 секунд** на пользователя. При превышении:
- Отправляет сообщение «⏳ Подождите немного и попробуйте снова.»
- Пропускает обработку апдейта

Реализация: `deque` (O(1) операции), ограничение размера словаря до `_MAX_BUCKETS=10_000` для защиты от утечки памяти.

---

#### `src/presentation/formatters/message_formatter.py` — Форматтер сообщений

Класс `MessageFormatter` — единый источник всех текстов в боте (~37 тыс. символов). Каждый метод:
1. Сначала пытается получить текст из `config.json` через `_tpl(key, default)`
2. Если не найден — использует встроенный дефолт
3. Поддерживает HTML-форматирование (жирный, код, ссылки)

Ключевые методы: `welcome_banner()`, `booking_success()`, `appointment_card_box()`, `admin_dashboard_summary()`, `admin_appointments_list()`, `reminder_card()`, `my_appointments_list_blocks()`, `notify_admin_new_booking()`, `nearby_slots_list()`, и десятки других.

---

## 4. База данных — таблицы и схема

SQLite файл: `data/manicure_bot.db`. Схема инициализируется автоматически при первом запуске.

### Таблицы

| Таблица | Назначение |
|---|---|
| `working_days` | Рабочие дни мастера (date, is_closed) |
| `time_slots` | Временные слоты в расписании (date, time, is_booked) |
| `appointments` | Записи клиентов (user_id, имя, телефон, дата, время, статус, услуга) |
| `users` | Все пользователи бота для рассылки (обновляется через middleware) |
| `blacklist` | Заблокированные пользователи (user_id, reason, created_at) |
| `waitlist` | Лист ожидания (user_id, date, UNIQUE(user_id, date)) |
| `workday_templates` | Именованные шаблоны расписания (name UNIQUE, slots JSON) |
| `backups` | История резервных копий (path, created_at) |
| `apscheduler_jobs` | Задачи планировщика APScheduler (создаётся автоматически SQLAlchemy) |

### PRAGMA-настройки

```sql
PRAGMA journal_mode = WAL;       -- параллельное чтение
PRAGMA foreign_keys = ON;        -- каскадные операции
PRAGMA synchronous = NORMAL;     -- баланс скорость/надёжность
PRAGMA cache_size = -8000;       -- 8 МБ кэш
PRAGMA temp_store = MEMORY;      -- временные данные в памяти
```

---

## 5. Функциональность для клиентов

### Главное меню (ReplyKeyboard)

```
┌─────────────────┬─────────────────┐
│  📅 Записаться  │  📋 Мои записи  │
├─────────────────┼─────────────────┤
│ 📆 Расписание   │ 🔔 Ближайшие   │
│                 │     слоты       │
├─────────────────┼─────────────────┤
│  📞 Контакты    │   💰 Цены       │
├─────────────────┼─────────────────┤
│  📤 Поделиться  │ 🔔 Уведомления  │
├─────────────────┴─────────────────┤
│    💅 Портфолио  (если задан URL) │
└───────────────────────────────────┘
```

### Пошаговая запись

1. **Выбор услуги** — из настроенного списка (маникюр, педикюр и т.д.)
2. **Выбор даты** — inline-календарь с подсветкой доступных дат (✅), недоступных (✖️) и прошедших
3. **Выбор времени** — кнопки свободных слотов (по 3 в ряд)
4. **Ввод имени** — валидация 2–100 символов
5. **Ввод телефона** — валидация формата (7–15 цифр, E.164)
6. **Комментарий** — опционально (кнопка «Пропустить»)
7. **Подтверждение** — карточка записи с рамкой, кнопки «✅ Подтвердить» / «❌ Отмена»

**Дополнительные возможности клиента:**
- Автозаполнение данных из предыдущей записи (кнопка «Использовать прошлые данные»)
- Перенос записи на другую дату/время (кнопка «🔄 Перенести» рядом с каждой записью)
- Вступление в лист ожидания на занятую дату — автоматическое уведомление при освобождении
- Отмена записи прямо из списка своих записей
- Подтверждение/отмена из напоминания (кнопки «✅ Приду» / «❌ Отменить»)
- Проверка подписки на канал (если `REQUIRED_CHANNEL` задан)

---

## 6. Функциональность для администратора

### Меню администратора (ReplyKeyboard)

```
┌──────────────────┬──────────────────┐
│  📋 Все записи   │  📅 Расписание   │
├──────────────────┼──────────────────┤
│ ➕ Добавить слот │ 🗓 Открыть день  │
├──────────────────┼──────────────────┤
│ 🔒 Закрыть день  │ ❌ Отменить     │
│                  │    запись        │
├──────────────────┼──────────────────┤
│  📊 Статистика   │   📢 Рассылка    │
├──────────────────┼──────────────────┤
│  ⬇️ Экспорт CSV  │ 📅 Открыть неделю│
├──────────────────┼──────────────────┤
│ 🔍 Найти клиента │ 🛑 Черный список │
├──────────────────┴──────────────────┤
│          🏠 Главное меню            │
└─────────────────────────────────────┘
```

### Возможности администратора

| Функция | Описание |
|---|---|
| **Просмотр записей** | Фильтр: сегодня / за неделю / все активные / все записи |
| **Отмена записи** | По ID + подтверждение + автоматическое уведомление клиента |
| **Массовая отмена** | Все записи на конкретную дату + уведомление каждому |
| **Управление расписанием** | Открыть/закрыть день, добавить/удалить слот |
| **Быстрое открытие недели** | 7 дней вперёд с учётом рабочих дней из настроек |
| **Статистика** | Общая: total/confirmed/cancelled/today/week |
| **Статистика по месяцам** | Пиковые дни недели и часы |
| **Рассылка** | HTML-текст → предпросмотр → отправка ВСЕМ пользователям |
| **Экспорт CSV** | Записи за диапазон дат в файл `.csv` |
| **Поиск клиента** | По имени или телефону |
| **История клиента** | Все визиты, статистика, последняя дата |
| **Чёрный список** | Заблокировать/разблокировать пользователя с причиной |
| **Шаблоны расписания** | Сохранить/применить/удалить шаблон |
| **Дайджест** | Ежедневная утренняя сводка (9:00 UTC) |
| **Бэкап** | Ежедневная резервная копия БД (2:00 UTC) |
| **Уведомление о слотах** | Предупреждение если < 3 свободных дней (10:00 UTC) |

---

## 7. Все кнопки и команды

### Команды Telegram

| Команда | Описание |
|---|---|
| `/start` | Приветствие + главное меню |
| `/help` | Справочное сообщение |
| `/cancel` | Сброс текущего действия |
| `/mybookings` | Быстрый доступ к своим записям |
| `/slots` | 5 ближайших свободных слотов |
| `/admin` | Вход в панель администратора |

### Callback-кнопки (InlineKeyboard)

| Callback data | Описание |
|---|---|
| `service:<name>` | Выбор услуги |
| `cal_day:<date>` | Выбор даты в календаре |
| `cal_prev:<year>:<month>` | Предыдущий месяц |
| `cal_next:<year>:<month>` | Следующий месяц |
| `slot:<date>:<time>` | Выбор времени |
| `skip_comment` | Пропустить комментарий |
| `booking_confirm` | Подтвердить запись |
| `booking_cancel` | Отменить процесс записи |
| `cancel_appt:<id>` | Отменить конкретную запись |
| `transfer_appt:<id>` | Начать перенос записи |
| `transfer_cal_day:<date>` | Выбор новой даты при переносе |
| `time:<time>` | Выбор нового времени при переносе |
| `join_waitlist:<date>` | Встать в лист ожидания |
| `waitlist_book:<date>:<time>` | Забронировать из уведомления waitlist |
| `use_prev` | Использовать прошлые данные |
| `reminder_yes:<id>` | Подтвердить приход (из напоминания) |
| `reminder_no:<id>` | Отменить из напоминания |
| `check_subscription` | Проверить подписку на канал |
| `main_menu` | Вернуться в главное меню |
| `book_start` | Вернуться к выбору даты |
| `admin_filter:<key>` | Фильтр записей (today/week/active/all) |
| `admin_confirm_cancel:<id>` | Подтвердить отмену (admin) |
| `admin_cancel_abort:<id>` | Отменить отмену (admin) |
| `admin_date:<date>` | Просмотр слотов дня (admin) |
| `admin_add_slot:<date>` | Добавить слот к дате (admin) |
| `admin_del_slot:<date>:<time>` | Начало удаления слота (admin) |
| `admin_confirm_del_slot:<date>:<time>` | Подтверждение удаления слота |
| `admin_toggle_day:<date>` | Переключить статус дня (admin) |
| `admin_broadcast_send` | Подтвердить отправку рассылки |
| `admin_broadcast_cancel` | Отменить рассылку |
| `admin_view_history` | Просмотр истории клиента |
| `admin_monthly_stats` | Статистика по месяцам |
| `admin_templates` | Управление шаблонами |
| `admin_block_user` | Начать блокировку пользователя |
| `admin_unblock_user` | Начать разблокировку |
| `admin_back_main` | Возврат в главное меню admin |
| `admin_back_schedule` | Возврат к списку расписания |
| `admin_main_menu` | Возврат в меню admin (через callback) |
| `confirm_cancel_all:<date>` | Подтверждение массовой отмены |

---

## 8. FSM — сценарии диалогов

### Сценарий записи клиента

```
/start или 📅 Записаться
    │
    ▼
[choosing_service] → выбор услуги (callback: service:*)
    │
    ▼
[choosing_date] → выбор даты в календаре (callback: cal_day:*)
    │
    ├─ нет слотов → предложение waitlist → КОНЕЦ
    │
    ▼
[choosing_time] → выбор времени (callback: slot:*)
    │
    ├─ есть имя/телефон в state → [entering_comment]
    │
    ▼
[entering_name] → ввод имени (текст)
    │
    ▼
[entering_phone] → ввод телефона (текст)
    │
    ▼
[entering_comment] → ввод комментария или «Пропустить»
    │
    ▼
[confirming] → карточка записи
    │
    ├─ booking_confirm → создание записи → уведомление → планирование напоминания → КОНЕЦ
    └─ booking_cancel → отмена → главное меню
```

### Сценарий переноса записи

```
callback: transfer_appt:<id>
    │
    ▼
[transferring_choosing_date] → выбор новой даты (callback: transfer_cal_day:*)
    │
    ▼
[transferring_choosing_time] → выбор нового времени (callback: time:*)
    │
    ▼
Отмена старой записи → Создание новой → Уведомление admin → КОНЕЦ
```

---

## 9. Планировщик задач (APScheduler)

| Задача | Расписание | Описание |
|---|---|---|
| `reminder_{id}_24` | По дате (дата визита − 24ч) | Напоминание за сутки |
| `reminder_{id}_2` | По дате (дата визита − 2ч) | Напоминание за 2 часа |
| `reminder_{id}_1` | По дате (дата визита − 1ч) | Напоминание за 1 час |
| `daily_digest` | Cron: 9:00 UTC | Утренняя сводка admin |
| `daily_backup` | Cron: 2:00 UTC | Бэкап БД |
| `weekly_archive` | Cron: вс 3:00 UTC | Архивирование старых отменённых записей |
| `insufficient_slots_check` | Cron: 10:00 UTC | Проверка наличия слотов (< 3 дней = предупреждение) |

Задачи персистентны (хранятся в SQLite через `SQLAlchemyJobStore`), при перезапуске восстанавливаются. Допустимое опоздание задачи: 1 час (`misfire_grace_time=3600`).

---

## 10. Уведомления

| Событие | Получатель | Содержание |
|---|---|---|
| Новая запись | Все администраторы | Имя, телефон, дата, время, ID, username |
| Новая запись | Telegram-канал | Краткое анонс (если `SCHEDULE_CHANNEL_ID` задан) |
| Отмена клиентом | Все администраторы | Имя, дата, время, телефон |
| Отмена администратором | Клиент | Дата, время, контакт с мастером |
| Напоминание за N часов | Клиент | Карточка с датой, временем, адресом + кнопки «✅ Приду» / «❌ Отменить» |
| Освободился слот | Пользователи из waitlist | Дата, время + кнопка «✅ Забронировать» |
| Ежедневный дайджест | Все администраторы | Статистика + список записей на сегодня |
| Мало слотов | Все администраторы | Предупреждение если < 3 свободных дней |

---

## 11. Быстрый старт — установка и запуск

### Требования

- Python 3.10+
- Telegram Bot Token (получить у [@BotFather](https://t.me/BotFather))
- Свой Telegram ID (узнать у [@userinfobot](https://t.me/userinfobot))

### Установка

```bash
# 1. Клонировать репозиторий
git clone https://github.com/KazymaAP/manicure_bot.git
cd manicure_bot

# 2. Создать виртуальное окружение
python -m venv venv
source venv/bin/activate        # Linux/macOS
# venv\Scripts\activate         # Windows

# 3. Установить зависимости
pip install -r requirements.txt

# 4. Создать файл конфигурации
cp .env.example .env

# 5. Отредактировать .env (ОБЯЗАТЕЛЬНО!)
nano .env                        # или любой редактор
```

### Минимальная настройка `.env`

```env
BOT_TOKEN=1234567890:AABBCCDDEEFFaabbccdd...   # от @BotFather
ADMIN_IDS=123456789                              # ваш Telegram ID
TIMEZONE=Europe/Moscow
```

### Запуск

```bash
python main.py
```

При первом запуске автоматически:
- Создаётся директория `data/`
- Создаётся файл БД `data/manicure_bot.db`
- Применяется схема таблиц
- Запускается планировщик
- Запускается health-check сервер на порту 8080

---

## 12. Настройка конфигурации (.env)

Полный список параметров с примерами:

```env
# ── ОБЯЗАТЕЛЬНО ──────────────────────────────────────
BOT_TOKEN=YOUR_BOT_TOKEN_HERE
ADMIN_IDS=123456789,987654321       # можно несколько через запятую

# ── База данных ──────────────────────────────────────
DB_PATH=data/manicure_bot.db

# ── Напоминания ──────────────────────────────────────
REMINDER_HOURS_BEFORE=24            # за 24 часа до визита
TIMEZONE=Europe/Moscow              # временная зона

# ── Ограничения ──────────────────────────────────────
MAX_APPOINTMENTS_PER_USER=1

# ── Канал подписки (необязательно) ───────────────────
REQUIRED_CHANNEL=@my_manicure_channel

# ── Канал расписания (необязательно) ─────────────────
SCHEDULE_CHANNEL_ID=-100123456789

# ── Портфолио (необязательно) ────────────────────────
PORTFOLIO_URL=https://www.instagram.com/my_nail_master/

# ── Контакты мастера ─────────────────────────────────
PHONE=+7 (999) 123-45-67
INSTAGRAM=@my_nails
ADDRESS=г. Москва, ул. Пушкина, д. 10
MAPS_LINK=https://yandex.ru/maps/-/...

# ── Redis FSM (необязательно) ────────────────────────
# REDIS_URL=redis://localhost:6379/0

# ── Приветственное фото (необязательно) ─────────────
WELCOME_PHOTO_URL=https://example.com/banner.jpg

# ── Услуги с ценами (JSON) ────────────────────────────
SERVICES={"маникюр": {"duration": 60, "price": 1500}, "педикюр": {"duration": 90, "price": 2000}}

# ── Рабочие дни (Пн-Сб) ─────────────────────────────
WORK_DAYS=[1, 2, 3, 4, 5, 6]

# ── Логирование ──────────────────────────────────────
LOG_LEVEL=INFO
LOG_FILE=bot.log

# ── Health-check ─────────────────────────────────────
HEALTH_PORT=8080
```

---

## 13. Настройка внешнего вида (config.json)

`config.json` позволяет изменить все тексты бота и список слотов по умолчанию без редактирования Python-кода:

```json
{
  "bot": {
    "name": "Записаться к Анне",
    "service_name": "педикюр",
    "master_name": "Анна",
    "welcome_emoji": "🦶"
  },
  "messages": {
    "welcome": "Привет, {name}! 🦶 Записываемся на педикюр?\n\nВыберите действие:",
    "booking_success_note": "Ждём вас! Напоминание придёт за {hours} ч. до визита."
  },
  "buttons": {
    "book": "📅 Записаться на педикюр",
    "my_appointments": "📋 Мои записи"
  },
  "schedule": {
    "days_ahead": 30,
    "default_time_slots": ["10:00", "12:00", "14:00", "16:00", "18:00"]
  }
}
```

---

## 14. Docker-деплой

### Сборка и запуск

```bash
# Создать .env из примера
cp .env.example .env
nano .env      # заполнить BOT_TOKEN и ADMIN_IDS

# Запустить
docker compose up -d

# Посмотреть логи
docker compose logs -f bot

# Остановить
docker compose down
```

### Что включает docker-compose.yml

- Контейнер `manicure_bot_v4` собирается из `Dockerfile`
- `restart: unless-stopped` — автоперезапуск при падении
- Volume `bot_data:/app/data` — данные БД и бэкапы сохраняются между перезапусками
- Порт `8080:8080` — health-check снаружи
- Healthcheck: `curl -f http://localhost:8080/health` каждые 30 секунд
- Опциональный Redis-сервис (закомментирован)

### Dockerfile (multi-stage)

- **Stage 1 (builder)**: `python:3.12-slim` + `build-essential` → устанавливает зависимости в `~/.local`
- **Stage 2 (runtime)**: чистый `python:3.12-slim` → копирует только установленные пакеты
- Директория `/app/data` создаётся с правами `755`
- `ENV PYTHONUNBUFFERED=1` — для корректного вывода логов

---

## 15. Тесты и CI

### Запуск тестов

```bash
# Установить dev-зависимости (pytest уже в requirements.txt)
pip install pytest pytest-asyncio

# Запустить все тесты
pytest tests/

# С подробным выводом
pytest tests/ -v
```

### Структура тестов

**`tests/unit/test_services/test_appointment_service.py`** — unit-тесты `AppointmentService` с mock-репозиториями:

| Тест | Сценарий |
|---|---|
| `test_create_booking_success` | Успешное создание записи |
| `test_create_booking_slot_already_booked` | Слот занят → `SlotAlreadyBookedError` |
| `test_create_booking_max_appointments_reached` | Превышен лимит → `MaxAppointmentsReachedError` |
| `test_cancel_by_user_success` | Успешная отмена клиентом |
| `test_cancel_by_user_no_appointment` | Нет активной записи → `None` |
| `test_get_statistics_empty` | Статистика при пустой БД |

### CI (GitHub Actions)

**`.github/workflows/mypy.yml`** — запускается на каждый push в `main` и `develop`:
- Проверяет тип Python: `3.11` и `3.12`
- Устанавливает зависимости из `requirements.txt`
- Запускает `mypy --strict src/`
- Запускает `mypy tests/`

### Настройки mypy (pyproject.toml)

```toml
[tool.mypy]
python_version = "3.10"
strict = true
warn_return_any = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
```

---

## 16. Зависимости и технологический стек

### Runtime-зависимости

| Библиотека | Версия | Зачем |
|---|---|---|
| `aiogram` | 3.13.1 | Telegram Bot API фреймворк |
| `pydantic` | 2.9.2 | Валидация данных, Settings |
| `pydantic-settings` | 2.6.1 | Загрузка настроек из .env |
| `apscheduler[sqlalchemy]` | 3.10.4 | Планировщик задач + персистентность |
| `SQLAlchemy` | 2.0.20 | SQLAlchemy Job Store для APScheduler |
| `python-dotenv` | 1.0.1 | Загрузка .env файла |
| `aiohttp` | 3.9.1 | HTTP health-check сервер |
| `tzdata` | 2024.1 | База данных часовых поясов (Linux/Docker) |

### Dev/CI-зависимости

| Библиотека | Зачем |
|---|---|
| `pytest` + `pytest-asyncio` | Unit-тесты |
| `mypy` | Строгая статическая типизация |
| `types-aiohttp` | Stub-пакет для mypy |

### Опциональные зависимости

| Библиотека | Как активировать | Зачем |
|---|---|---|
| `redis` | `pip install redis` | Redis FSM Storage (для продакшн) |

### Технологические решения

- **Python 3.10+** — использует `match`, `X | Y` тип-юнионы, `dataclass(slots=True)`
- **aiogram 3.x** — асинхронный, FSM через `StatesGroup`, middleware через `BaseMiddleware`
- **SQLite + WAL** — без внешних зависимостей, персистентность, thread-safe
- **asyncio.to_thread** — синхронные SQLite-операции не блокируют event loop
- **BEGIN IMMEDIATE** — атомарные транзакции при создании записи (защита от race condition)
- **lru_cache** — кэширование настроек и config.json, один read при старте
- **Singleton DatabaseManager** — одно соединение на поток, thread-local storage

---

## Структура данных: Пример полного потока создания записи

```
Клиент нажимает "📅 Записаться"
    │
    ├─ user_handler.start_booking()
    │   ├─ state.clear()  # сброс старого FSM
    │   ├─ проверка подписки (если REQUIRED_CHANNEL)
    │   ├─ state → BookingFSM.choosing_service
    │   └─ BookingKeyboard.service_selection(settings.services)
    │
    ├─ user_handler.choose_service() [callback: service:маникюр]
    │   ├─ state.update_data(service="маникюр")
    │   ├─ sched_service.get_available_dates_async() → SQL в asyncio.to_thread
    │   ├─ state → BookingFSM.choosing_date
    │   └─ CalendarKeyboard.build(year, month, available_dates)
    │
    ├─ user_handler.choose_date() [callback: cal_day:2025-12-15]
    │   ├─ sched_service.get_available_slots("2025-12-15")
    │   ├─ state.update_data(chosen_date="2025-12-15")
    │   ├─ state → BookingFSM.choosing_time
    │   └─ BookingKeyboard.time_slots("2025-12-15", slots)
    │
    ├─ user_handler.choose_time() [callback: slot:2025-12-15:10-00]
    │   ├─ time_str = "10:00"
    │   ├─ state.update_data(chosen_time="10:00")
    │   ├─ state → BookingFSM.entering_name
    │   └─ "Введите ваше имя:"
    │
    ├─ user_handler.enter_name() [text: "Мария"]
    │   ├─ валидация 2-100 символов
    │   ├─ state.update_data(client_name="Мария")
    │   ├─ state → BookingFSM.entering_phone
    │   └─ "Введите номер телефона:"
    │
    ├─ user_handler.enter_phone() [text: "+79991234567"]
    │   ├─ валидация E.164
    │   ├─ state.update_data(phone="+79991234567")
    │   ├─ state → BookingFSM.entering_comment
    │   └─ "Комментарий? (Пропустить ➡️)"
    │
    ├─ user_handler.skip_comment() [callback: skip_comment]
    │   ├─ state.update_data(comment=None)
    │   └─ _show_confirmation() → карточка записи
    │
    └─ user_handler.confirm_booking() [callback: booking_confirm]
        ├─ appt_service.create_appointment(...)
        │   └─ AppointmentService.create_booking(dto)
        │       ├─ BEGIN IMMEDIATE
        │       ├─ COUNT активных записей
        │       ├─ CHECK blacklist
        │       ├─ book_slots_with_conn() → is_booked=1
        │       └─ INSERT INTO appointments
        │
        ├─ notif_service.notify_admin_new_booking(appt_id)
        ├─ reminder_service.schedule_reminder(appt_id, ...)
        └─ "✅ Запись создана! Ждём вас 15 декабря в 10:00"
```

---