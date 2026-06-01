# manicure_bot v4 — Telegram бот для записи на маникюр

## 📋 Обзор проекта

Telegram-бот для онлайн-записи клиентов на маникюр/педикюр к мастеру.
Построен на **aiogram 3.x**, **SQLite**, **APScheduler**, **Pydantic v2**.

---

## 🚀 Быстрый старт

### 1. Клонирование и настройка
```bash
git clone https://github.com/KazymaAP/manicure_bot.git
cd manicure_bot
cp .env.example .env
# Отредактируй .env: укажи BOT_TOKEN и ADMIN_IDS
```

### 2. Установка зависимостей
```bash
pip install -r requirements.txt
```

### 3. Запуск
```bash
python main.py
```

### 4. Запуск через Docker
```bash
docker-compose up -d
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
| `REDIS_URL` | Нет | URL Redis для FSM (рекомендуется для production) |
| `METRICS_TOKEN` | Нет | Bearer-токен для `/metrics` HTTP endpoint |
| `SERVICES` | Нет | JSON словарь услуг с ценами и длительностью |
| `PORTFOLIO_URL` | Нет | URL портфолио мастера |
| `REQUIRED_CHANNEL` | Нет | @channel для обязательной подписки |

---

## 🔧 Исправленные баги (аудит)

### 🔴 Критические (C)

| ID | Описание | Статус |
|---|---|---|
| **C-3** | SQL-инъекция в `search_by_client` через LIKE `%query%` | ✅ Исправлено — экранирование `%`, `_`, `\` + ESCAPE |
| **C-5** | Нет аутентификации на `/metrics` HTTP endpoint | ✅ Исправлено — Bearer-токен (`METRICS_TOKEN`) |
| **C-6** | Race condition при переносе записи — возможна потеря записи | ✅ Исправлено — правильный порядок операций с восстановлением |
| **C-7** | Валидация телефона только в хендлере (обходится) | ✅ Исправлено — валидация в `CreateBookingDTO.__post_init__` |
| **C-8** | Несоответствие версий в `pyproject.toml` vs `requirements.txt` | ✅ Исправлено — синхронизированы версии dev-зависимостей |

### 🟠 Высокие (H)

| ID | Описание | Статус |
|---|---|---|
| **H-3** | Токен бота в логах при ошибке валидации | ✅ Исправлено — `SecretStr` для `bot_token` |
| **H-4** | Нет ограничения длины текста рассылки | ✅ Исправлено — макс. 4000 символов |
| **H-5** | `docker-compose.yml` без версии, без сети | ✅ Исправлено — `version: "3.9"`, явная сеть |
| **H-6** | APScheduler игнорирует настройку `timezone` | ✅ Исправлено — `timezone=self._timezone` во все `CronTrigger` |
| **H-7** | Нет обработки `TelegramRetryAfter` (flood control) | ✅ Исправлено — retry с `asyncio.sleep(retry_after)` |
| **H-8** | HealthServer слушает `0.0.0.0` — открыт наружу | ✅ Исправлено — биндится на `127.0.0.1` |
| **H-9** | Нет пагинации в списке записей администратора | ✅ Исправлено — ограничение 20 записей + счётчик |
| **H-10** | Docker образ запускается от `root` | ✅ Исправлено — создан пользователь `botuser` |

---

## 📁 Структура проекта

```
manicure_bot/
├── main.py                    # Точка входа
├── requirements.txt           # Зависимости
├── pyproject.toml             # Конфигурация проекта
├── .env.example               # Шаблон конфигурации
├── config.json                # Настраиваемые тексты бота
├── Dockerfile                 # Docker образ (непривилегированный пользователь)
├── docker-compose.yml         # Docker Compose конфигурация
├── migrations/                # SQL миграции
│   ├── 001_initial.sql
│   ├── 002_add_fk_time_slots.sql
│   └── 003_add_waitlist_users_tables.sql
├── src/
│   ├── application/
│   │   ├── dto/               # Data Transfer Objects
│   │   ├── services/          # Бизнес-сервисы
│   │   └── use_cases/
│   ├── config/                # Настройки (Pydantic)
│   ├── domain/                # Доменные модели, исключения, enum
│   ├── infrastructure/        # БД, репозитории, HTTP
│   └── presentation/          # Хендлеры, клавиатуры, middleware
└── tests/                     # Тесты
```

---

## 🔒 Безопасность

- **Токен бота** хранится как `SecretStr` — не попадает в логи
- **`/metrics`** защищён Bearer-токеном (`METRICS_TOKEN` в `.env`)
- **Health server** биндится только на `127.0.0.1`
- **Docker** запускается от непривилегированного пользователя `botuser`
- **LIKE-запросы** правильно экранируют `%`, `_`, `\`

---

## 📊 Технический стек

- **Python**: 3.12
- **Telegram**: aiogram 3.13.1
- **База данных**: SQLite (aiosqlite-совместимый WAL-режим)
- **Планировщик**: APScheduler 3.10.4 (с SQLAlchemy)
- **Настройки**: Pydantic v2 + pydantic-settings
- **HTTP**: aiohttp (health server)
- **FSM**: MemoryStorage (dev) / Redis (production)

---

## 📮 Контакты и поддержка

При вопросах обращайтесь к администратору через Telegram бота.
