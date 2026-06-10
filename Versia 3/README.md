# 💅 Manicure Bot

Telegram-бот для онлайн-записи на маникюр. Клиент выбирает услугу, дату и время, получает подтверждение и напоминания.

---

## Архитектура

```
src/
├── application/          # Сервисный слой (AppointmentService, ReminderService, ...)
├── config/               # Settings (Pydantic), DI-контейнер, _load_config_json
├── domain/               # Модели, исключения, FSM-состояния (BookingFSM, AdminFSM)
├── infrastructure/       # БД (SQLite + DatabaseManager), репозитории, HTTP health server
└── presentation/
    ├── formatters/        # MessageFormatter — все HTML-тексты бота
    ├── handlers/          # 5 роутеров: admin, user, common, extended_features, final_features
    ├── keyboards/         # InlineKeyboard: booking, admin, calendar, main_menu, notifications
    └── middlewares/       # LoggingMiddleware, RateLimitMiddleware, AdminOnlyMiddleware
```

### 5 роутеров (хендлеры)
| Файл | Назначение |
|------|-----------|
| `admin_handler.py` | Панель администратора: записи, расписание, клиенты, настройки, рассылка |
| `user_handler.py` | FSM-процесс записи клиента: услуга → дата → время → данные → подтверждение |
| `common_handler.py` | `/start`, `/help`, контакты, цены, общие команды |
| `extended_features_handler.py` | Перенос записи, лист ожидания, шаблоны расписания, статистика по месяцам |
| `final_features_handler.py` | `/slots`, `/mybookings`, уведомления, расписание, рассылка, inline режим |

### Ключевые сервисы
- **APScheduler** (AsyncIOScheduler) — напоминания клиентам
- **Cloudflare/aiohttp health server** — `/health` и `/metrics` с Bearer-токеном
- **Rate limiting middleware** — защита от спама
- **config.json** — рантайм-настройки (приветствие, услуги, фото) без перезапуска

---

## Установка

```bash
# 1. Создать .env из шаблона
cp .env.example .env
# Заполнить BOT_TOKEN, ADMIN_IDS и т.д.

# 2. Установить зависимости
pip install -r requirements.txt

# 3. Применить миграции
python main.py  # создаёт БД автоматически при первом запуске

# 4. Запустить
python main.py
```

### Docker
```bash
docker compose up -d
# или с dev-настройками:
docker compose -f docker-compose.dev.yml up
```

---

## Переменные окружения

| Переменная | Описание | Обязательна |
|-----------|---------|------------|
| `BOT_TOKEN` | Токен бота (@BotFather) | ✅ |
| `ADMIN_IDS` | ID администраторов через запятую | ✅ |
| `DB_PATH` | Путь к SQLite-файлу (default: `data/bot.db`) | — |
| `TIMEZONE` | Часовой пояс (default: `Europe/Moscow`) | — |
| `REMINDER_HOURS_BEFORE` | За сколько часов напоминание (default: `24`) | — |
| `REQUIRED_CHANNEL` | @канал для обязательной подписки | — |
| `HEALTH_PORT` | Порт health server (default: `8080`) | — |
| `METRICS_TOKEN` | Bearer-токен для `/metrics` | — |
| `REDIS_URL` | URL Redis (для FSM storage) | — |

---

## Команды

| Команда | Описание |
|---------|---------|
| `/start` | Запустить бота |
| `/help` | Справка + список команд |
| `/mybookings` | Мои активные записи |
| `/slots` | Ближайшие 5 свободных слотов |
| `/cancel` | Отменить текущее FSM-действие |
| `/admin` | Войти в панель администратора |

---

## Исправления (аудит 2026-06)

### Критические (Блок 1)
- **FIX #1**: XSS-инъекция — все пользовательские данные обёрнуты в `html.escape()` / `_escape()` в `MessageFormatter`
- **FIX #2**: Guard `if message.from_user is None: return` во всех message-хендлерах
- **FIX #3**: Guard `if callback.from_user is None: await callback.answer(); return` во всех callback-хендлерах
- **FIX #4**: `_broadcast_tasks` перенесён на уровень модуля (было: внутри фабричной функции)
- **FIX #5**: Валидация `appt_id` — проверка диапазона `0 < appt_id < 2_147_483_647`
- **FIX #6**: Проверка прав в `admin_monthly_stats`, `admin_templates`, `admin_save_template`, `admin_delete_template`, `admin_apply_template`
- **FIX #7**: Guard на `admin_back_clients` — теперь требует прав администратора
- **FIX #8**: `delete_by_ids` использует батчинг по 500 записей (SQLite LIMIT_VARIABLE_NUMBER)

### Дублирование кода (Блок 2)
- **FIX #9**: `admin_edit_welcome` — заменён прямой `open()` на `_load_config()`
- **FIX #11**: `AdminOnlyMiddleware` создан в `middlewares/admin_middleware.py`

### Безопасность (Блок 3)
- **FIX #14**: `_do_broadcast` содержит повторную проверку текста `len(text) > 4096`
- **FIX #15**: Таймаут 5 сек на `get_statistics()` в `/metrics` health endpoint
- **FIX #16**: `restore_reminders()` очищает устаревшие jobs перед восстановлением
- **FIX #18**: Валидация имени услуги в `admin_del_svc_confirm`
- **FIX #19**: Проверка `message.text is not None` в `admin_save_template_name`
- **FIX #20**: Лимит 50 шаблонов расписания

### Недостающий функционал (Блок 4)
- **FIX #21**: Кнопка «🔄 Перенести» добавлена в `BookingKeyboard.reminder_actions()`
- **FIX #22**: `/slots` показывает список + кнопку «Записаться» (было: CalendarKeyboard)
- **FIX #24**: `help_text()` обновлён — добавлены `/slots`, `/mybookings`, уведомления
- **FIX #25**: Хендлеры `calendar_ignore` и `transfer_cal_ignore` для `BookingFSM.transferring_choosing_date`

### Упаковка (Блок 5)
- **FIX #27**: Новые тесты в `tests/unit/test_security/test_xss_escaping.py`
- **FIX #29**: `.dockerignore` — исключены `.env` файлы

---

## Запуск тестов

```bash
# Все тесты
python -m pytest tests/ -v --tb=short

# Только security тесты
python -m pytest tests/unit/test_security/ -v

# Тесты callback покрытия
python -m pytest tests/unit/test_handlers/ -v

# С покрытием
python -m pytest tests/ --cov=src --cov-report=html
```

---

## Развёртывание

Подробные инструкции: [`DEPLOY.md`](DEPLOY.md)

**Платформа:** Docker + systemd  
**БД:** SQLite (файл `data/bot.db`, монтируется как volume)  
**Напоминания:** APScheduler с SQLAlchemyJobStore (персистентность через restart)
