# manicure_bot v4 — Telegram бот для записи на маникюр

## 📋 Обзор проекта

Telegram-бот для онлайн-записи клиентов на маникюр/педикюр к мастеру.  
Построен на **aiogram 3.x**, **SQLite**, **APScheduler**, **Pydantic v2**.

---

## ⚠️ ВАЖНЫЕ ПРЕДУПРЕЖДЕНИЯ

> **MemoryStorage**: По умолчанию FSM-состояния хранятся в памяти (MemoryStorage).
> При перезапуске бота пользователи, находящиеся в середине записи, потеряют прогресс.
> Для продакшн-окружения настройте Redis: `REDIS_URL=redis://localhost:6379/0`.

> **Webhook**: Бот работает ТОЛЬКО в режиме long polling. Webhook не реализован.
> Не настраивай WEBHOOK_URL — он игнорируется.

> **Inline mode**: Для работы функции поиска через `@bot` нужно включить inline mode
> в @BotFather: `/setinline` → выбери бота → напиши подсказку.

> **Required channel**: Если используешь REQUIRED_CHANNEL — добавь бота в канал
> как **администратора** с правом просмотра участников. Иначе проверка подписки не работает.

---

## 🚀 Быстрый старт

### 1. Клонирование и настройка
```bash
git clone https://github.com/KazymaAP/manicure_bot.git
cd manicure_bot
cp .env.example .env
# Отредактируй .env: укажи BOT_TOKEN и ADMIN_IDS (минимум)
```

### 2. Установка зависимостей
```bash
pip install -r requirements.txt
```

### 3. Запуск
```bash
python main.py
```

### 4. Запуск через Docker (рекомендуется)
```bash
docker-compose up -d
# Логи:
docker-compose logs -f bot
```

---

## ⚙️ Конфигурация (.env)

| Переменная | Обязательная | Описание |
|---|---|---|
| `BOT_TOKEN` | ✅ | Токен бота от @BotFather |
| `ADMIN_IDS` | ✅ | Telegram ID администратора(ов) через запятую |
| `DB_PATH` | Нет | Путь к SQLite файлу (default: `data/manicure_bot.db`) |
| `TIMEZONE` | Нет | Временная зона (default: `Europe/Moscow`) |
| `REMINDER_HOURS_BEFORE` | Нет | За сколько часов отправлять напоминание (default: 24) |
| `MAX_APPOINTMENTS_PER_USER` | Нет | Макс. кол-во активных записей (default: 1) |
| `REDIS_URL` | Нет | URL Redis для FSM (⚠️ рекомендуется для production) |
| `METRICS_TOKEN` | Нет | Bearer-токен для `/metrics` HTTP endpoint |
| `SERVICES` | Нет | JSON словарь услуг с ценами и длительностью |
| `PORTFOLIO_URL` | Нет | URL портфолио мастера (WebApp кнопка) |
| `REQUIRED_CHANNEL` | Нет | @channel для обязательной подписки (бот = admin канала!) |
| `SCHEDULE_CHANNEL_ID` | Нет | ID канала для публикации расписания (-1 = отключено) |
| `PHONE` | Нет | Телефон мастера |
| `INSTAGRAM` | Нет | Instagram / соцсеть мастера |
| `ADDRESS` | Нет | Адрес студии |
| `MAPS_LINK` | Нет | Ссылка на карту |

### Настройка SERVICES (пример)
```bash
# В .env — весь JSON в одну строку, двойные кавычки:
SERVICES={"маникюр": {"duration": 60, "price": 1200}, "педикюр": {"duration": 90, "price": 1500}, "маникюр+педикюр": {"duration": 120, "price": 2500}}
```

---

## 📱 Интерфейс бота

### Главное меню (клиент)
| Кнопка | Описание |
|---|---|
| 📅 Записаться | Начать процесс записи (выбор услуги → дата → время → подтверждение) |
| 📋 Мои записи | Посмотреть активные записи, отменить или перенести |
| 📆 Расписание | Посмотреть ближайшие доступные даты |
| 🔔 Ближайшие слоты | Показать ближайшие 5 свободных слотов |
| 📞 Контакты | Контактная информация мастера |
| 💰 Цены | Прайс-лист услуг |
| 📤 Поделиться | Получить реферальную ссылку на бота |
| 🔔 Уведомления | Управление напоминаниями (24ч / 2ч / 1ч) |
| 💅 Портфолио | WebApp с портфолио (если настроен PORTFOLIO_URL) |

### Главное меню (администратор)
| Кнопка | Описание |
|---|---|
| 📋 Все записи | Фильтрация и просмотр записей (сегодня/неделя/активные/все) |
| 📅 Расписание | Управление рабочими днями и слотами |
| ➕ Добавить слот | Добавить временной слот на дату |
| 🗓 Открыть день / 🔒 Закрыть день | Управление статусом рабочего дня |
| ❌ Отменить запись | Отменить запись по ID |
| 📊 Статистика | Общая статистика (в меню есть "📊 Статистика по месяцам") |
| 📢 Рассылка | Отправить сообщение всем пользователям |
| ⬇️ Экспорт CSV | Экспорт записей за период |
| 📅 Открыть неделю | Открыть 7 рабочих дней вперёд |
| 🔍 Найти клиента | Поиск по имени/телефону |
| 🛑 Черный список | Управление блокировками |
| 🚫 Массовая отмена | Отменить все записи на выбранную дату |

### Inline-режим
```
@ваш_бот 2025-06
# Покажет доступные даты в июне 2025 с количеством слотов
```
⚠️ Требует включения inline mode в @BotFather (`/setinline`)

---

## 🔧 Исправленные баги (полный список)

### 🔴 Критические

| ID | Описание | Статус |
|---|---|---|
| **БАГ-КРИТ-01** | Конфликт FSM waiting_for_search_query — история посещений никогда не работала | ✅ Исправлено — отдельное состояние `waiting_for_history_query` |
| **БАГ-КРИТ-02** | Несоответствие ключей `transfer_source` vs `transfer_source_appt_id` — старая запись не отменялась | ✅ Исправлено — унифицирован ключ `transfer_source_appt_id` |
| **БАГ-КРИТ-03** | Прямой доступ к `_schedule_repo` из хендлера — нарушение DDD | ✅ Исправлено — добавлен публичный метод `ScheduleService.delete_workday_template()` |
| **БАГ-КРИТ-04** | Дублирование хендлеров массовой отмены — мёртвый код в меню | ✅ Исправлено — единый inline-поток, добавлена кнопка "🚫 Массовая отмена" |
| **БАГ-КРИТ-05** | Прямые sqlite3.connect() в final_features_handler — утечки соединений | ✅ Исправлено — используется DatabaseManager через container.db |
| **C-3** | SQL-инъекция через LIKE `%query%` | ✅ Исправлено — экранирование спецсимволов |
| **C-5** | Нет аутентификации на /metrics | ✅ Исправлено — Bearer-токен |
| **C-6** | Race condition при переносе | ✅ Исправлено — правильный порядок операций |
| **C-7** | Валидация телефона обходится | ✅ Исправлено — валидация в DTO |
| **C-8** | Несоответствие версий pyproject.toml | ✅ Исправлено |

### 🟠 Высокие

| ID | Описание | Статус |
|---|---|---|
| **БАГ-ВЫСОК-01** | Нет ограничения минимальной длины поискового запроса | ✅ Исправлено — минимум 2 символа |
| **БАГ-ВЫСОК-02** | docker-compose.yml и Dockerfile перепутаны | ✅ Исправлено — файлы разделены |
| **БАГ-ВЫСОК-03** | Нет пагинации в результатах поиска клиентов | ✅ Исправлено — первые 10 результатов + счётчик |
| **БАГ-ВЫСОК-04** | Архивирование только логирует, не удаляет | ✅ Исправлено — экспорт в CSV + удаление из БД |
| **БАГ-ВЫСОК-05** | Напоминания не учитывают настройки пользователя | ✅ Исправлено — проверка notifications_enabled перед отправкой |
| **БАГ-ВЫСОК-06** | Кнопки "Расписание", "Цены", "Контакты", "Поделиться", "Уведомления" не в меню | ✅ Исправлено — все кнопки присутствуют в MainMenuKeyboard |
| **БАГ-ВЫСОК-07** | HTML-инъекция в истории клиента | ✅ Исправлено — html.escape() для всех пользовательских данных |
| **БАГ-ВЫСОК-08** | Webhook поля в Settings но webhook не реализован | ✅ Исправлено — поля помечены deprecated, добавлено предупреждение |
| **H-3..H-10** | Баги из первого аудита | ✅ Исправлено |

### 🟡 Средние

| ID | Описание | Статус |
|---|---|---|
| **БАГ-СРЕД-01** | Inline mode требует включения в BotFather | ✅ Задокументировано |
| **БАГ-СРЕД-02** | Невидимые unicode-символы в тексте шаблонов | ✅ Исправлено |
| **БАГ-СРЕД-03** | Waitlist не очищается после бронирования | ✅ Исправлено — DELETE FROM waitlist WHERE user_id = ? |
| **БАГ-СРЕД-04** | Кнопка "Статистика по месяцам" не подключена к UI | ✅ Исправлено — добавлена в appointments_filter |
| **БАГ-СРЕД-05** | Нет валидации даты при переносе (перенос на тот же день) | ✅ Исправлено — проверка transfer_old_date == new_date |
| **БАГ-СРЕД-06** | Предупреждение о MemoryStorage | ✅ Задокументировано в README и .env.example |

---

## 📁 Структура проекта

```
manicure_bot/
├── main.py                    # Точка входа
├── requirements.txt           # Зависимости
├── pyproject.toml             # Конфигурация проекта
├── .env.example               # Шаблон конфигурации (ОБЯЗАТЕЛЬНО заполнить .env)
├── config.json                # Настраиваемые тексты и параметры бота
├── Dockerfile                 # Docker образ (непривилегированный пользователь botuser)
├── docker-compose.yml         # Docker Compose конфигурация
├── migrations/                # SQL миграции базы данных
│   ├── 001_initial.sql
│   ├── 002_add_fk_time_slots.sql
│   └── 003_add_waitlist_users_tables.sql
└── src/
    ├── application/
    │   ├── dto/               # Data Transfer Objects (CreateBookingDTO, BookingResultDTO)
    │   ├── services/          # Бизнес-сервисы
    │   │   ├── appointment_service.py  # Логика записей
    │   │   ├── schedule_service.py     # Логика расписания
    │   │   ├── reminder_service.py     # APScheduler напоминания
    │   │   ├── notification_service.py # Отправка Telegram сообщений
    │   │   └── backup_service.py       # Резервное копирование БД
    │   └── use_cases/         # Use cases (booking flow)
    ├── config/
    │   ├── dependencies.py    # DI-контейнер
    │   ├── settings.py        # Pydantic v2 настройки из .env
    │   └── logging_config.py  # Конфигурация логирования
    ├── domain/
    │   ├── enums/             # FSM состояния, статусы
    │   ├── exceptions/        # Доменные исключения
    │   └── models/            # Доменные модели (Appointment, TimeSlot, WorkingDay)
    ├── infrastructure/
    │   ├── database/          # DatabaseManager (SQLite WAL, per-thread connections)
    │   ├── http/              # Health-check сервер (127.0.0.1:8080)
    │   └── repositories/      # Репозитории данных (AppointmentRepo, ScheduleRepo)
    └── presentation/
        ├── handlers/          # aiogram хендлеры (admin, user, extended, final, common)
        ├── keyboards/         # Клавиатуры (main_menu, admin, booking, calendar)
        ├── formatters/        # MessageFormatter (HTML-форматирование)
        ├── middlewares/       # Rate limit, logging
        └── constants.py       # Константы (названия месяцев и т.д.)
```

---

## 🐳 Деплой через Docker (рекомендуется)

```bash
# 1. Скопируй конфигурацию
cp .env.example .env
# Отредактируй .env

# 2. Запусти
docker-compose up -d

# 3. Проверь логи
docker-compose logs -f bot

# 4. Остановка
docker-compose down
```

## 🖥️ Деплой на VPS (без Docker)

```bash
# 1. Обновление системы
sudo apt update && sudo apt upgrade -y

# 2. Python 3.11+
sudo apt install python3.11 python3.11-venv python3-pip -y

# 3. Клонирование проекта
git clone https://github.com/KazymaAP/manicure_bot.git
cd manicure_bot

# 4. Виртуальное окружение
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 5. Конфигурация
cp .env.example .env
nano .env  # Заполни BOT_TOKEN и ADMIN_IDS

# 6. Автозапуск через systemd
sudo nano /etc/systemd/system/manicure_bot.service
```

`/etc/systemd/system/manicure_bot.service`:
```ini
[Unit]
Description=Manicure Telegram Bot
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/home/user/manicure_bot
ExecStart=/home/user/manicure_bot/venv/bin/python main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable manicure_bot
sudo systemctl start manicure_bot
sudo systemctl status manicure_bot
```

---

## 🔍 Проверка работоспособности

```bash
# Health-check (бот должен отвечать)
curl http://localhost:8080/health

# Метрики (если настроен METRICS_TOKEN)
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:8080/metrics
```

---

## 📊 Модели данных

| Таблица | Назначение |
|---|---|
| `appointments` | Записи клиентов (id, user_id, date, time, service, status) |
| `working_days` | Рабочие дни (date, is_closed) |
| `time_slots` | Временные слоты (date, time, is_booked) |
| `waitlist` | Лист ожидания (user_id, date) |
| `users` | Все пользователи + настройки уведомлений |
| `blacklist` | Заблокированные пользователи |
| `workday_templates` | Шаблоны расписания |
| `backups` | Метаданные резервных копий |

---

## 🏗️ Архитектура

Проект построен по принципам **DDD (Domain-Driven Design)**:

- **Domain**: доменные модели, исключения, FSM-состояния
- **Application**: сервисы, use cases, DTO — бизнес-логика без зависимостей на фреймворк
- **Infrastructure**: репозитории SQLite, подключение к БД, HTTP сервер
- **Presentation**: aiogram хендлеры, клавиатуры, форматтеры

**DI-контейнер** (`Container`) управляет созданием всех сервисов и передаёт зависимости.

---

Последнее обновление: 2026-06-01 | Версия: 4.1 (после аудита и исправления багов)
