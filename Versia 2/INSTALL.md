# 📦 INSTALL.md — Пошаговая инструкция установки

## Требования

- Python 3.10 или выше
- pip 22+
- SQLite 3.35+ (входит в Python)
- Linux/macOS/Windows (рекомендуется Linux/Ubuntu)

---

## 1. Установка системных зависимостей (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git
```

---

## 2. Клонирование репозитория

```bash
git clone https://github.com/KazymaAP/manicure_bot.git
cd manicure_bot
```

---

## 3. Создание виртуального окружения

```bash
python3 -m venv .venv
source .venv/bin/activate      # Linux/macOS
# .venv\Scripts\activate       # Windows
```

---

## 4. Установка зависимостей

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

> **Примечание**: если возникает конфликт версий — установите в два этапа:
> ```bash
> pip install aiogram==3.13.1 pydantic-settings==2.7.0
> pip install -r requirements.txt
> ```

---

## 5. Настройка переменных окружения

```bash
cp .env.example .env
nano .env   # или любой другой редактор
```

**Обязательные поля** в `.env`:

```env
BOT_TOKEN=ваш_токен_от_BotFather
ADMIN_IDS=ваш_telegram_id
```

Узнать свой Telegram ID: напишите боту [@userinfobot](https://t.me/userinfobot).

---

## 6. Создание базы данных

База данных создаётся автоматически при первом запуске. Директория `data/` будет создана автоматически.

---

## 7. Первый запуск

```bash
python main.py
```

Или через скрипт автонастройки:

```bash
python setup_master.py
```

---

## 8. Запуск в фоновом режиме (production)

### Вариант 1: systemd (рекомендуется)

```bash
sudo nano /etc/systemd/system/manicure_bot.service
```

Содержимое файла:
```ini
[Unit]
Description=Manicure Telegram Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/manicure_bot
ExecStart=/home/ubuntu/manicure_bot/.venv/bin/python main.py
Restart=on-failure
RestartSec=10
EnvironmentFile=/home/ubuntu/manicure_bot/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable manicure_bot
sudo systemctl start manicure_bot
sudo systemctl status manicure_bot
```

### Вариант 2: Docker

```bash
cp .env.example .env
nano .env

docker-compose up -d
docker-compose logs -f
```

### Вариант 3: Docker (разработка с hot-reload)

```bash
docker-compose -f docker-compose.dev.yml up --build
```

---

## 9. Проверка работоспособности

```bash
# Health-check (если запущен health-сервер)
curl http://localhost:8080/health

# Логи (systemd)
sudo journalctl -u manicure_bot -f

# Логи (Docker)
docker-compose logs -f bot
```

---

## 10. Обновление

```bash
git pull
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart manicure_bot   # если systemd
```

---

## Переменные окружения — полная таблица

| Переменная | Обязательная | По умолчанию | Описание |
|---|---|---|---|
| `BOT_TOKEN` | ✅ | — | Токен Telegram бота от @BotFather |
| `ADMIN_IDS` | ✅ | — | ID администраторов через запятую |
| `DB_PATH` | ❌ | `data/manicure_bot.db` | Путь к SQLite файлу |
| `TIMEZONE` | ❌ | `UTC` | Временная зона (`Europe/Moscow`) |
| `REMINDER_HOURS_BEFORE` | ❌ | `24` | Напоминание за N часов (1–72) |
| `MAX_APPOINTMENTS_PER_USER` | ❌ | `1` | Макс. записей у клиента (1–10) |
| `SCHEDULE_DAYS_AHEAD` | ❌ | `30` | Горизонт расписания (дней) |
| `REQUIRED_CHANNEL` | ❌ | — | Канал для обязательной подписки |
| `SCHEDULE_CHANNEL_ID` | ❌ | `-1` | ID канала публикации расписания |
| `PHONE` | ❌ | — | Телефон мастера |
| `INSTAGRAM` | ❌ | — | Instagram мастера |
| `ADDRESS` | ❌ | — | Адрес студии |
| `MAPS_LINK` | ❌ | — | Ссылка на карту |
| `PORTFOLIO_URL` | ❌ | — | URL портфолио (кнопка в меню) |
| `WELCOME_PHOTO_URL` | ❌ | — | Фото в приветствии |
| `REDIS_URL` | ❌ | — | Redis для FSM (production) |
| `HEALTH_PORT` | ❌ | `8080` | Порт health-check сервера |
| `METRICS_TOKEN` | ❌ | — | Bearer-токен для `/metrics` |
| `LOG_LEVEL` | ❌ | `INFO` | Уровень логов |
| `LOG_FILE` | ❌ | `bot.log` | Файл логов |

---

## Решение частых проблем

### `BOT_TOKEN must be set`
Убедитесь что в `.env` установлен `BOT_TOKEN`.

### `ADMIN_IDS не настроены`
Установите `ADMIN_IDS=ваш_id` в `.env`. ID узнать у @userinfobot.

### `OperationalError: no such table`
База создаётся автоматически. Убедитесь что `DB_PATH` указывает в существующую папку, или создайте: `mkdir -p data`.

### `ResolutionImpossible` при установке зависимостей
```bash
pip install aiogram==3.13.1 pydantic-settings==2.7.0
pip install -r requirements.txt
```
