# DEPLOY.md — Инструкция по запуску бота на VPS

## Минимальные требования VPS

| Параметр | Минимум | Рекомендуется |
|----------|---------|---------------|
| CPU | 1 vCPU | 2 vCPU |
| RAM | 512 МБ | 1 ГБ |
| Диск | 5 ГБ SSD | 10 ГБ SSD |
| ОС | Ubuntu 20.04 | Ubuntu 22.04 LTS |
| Сеть | 10 Мбит/с | 100 Мбит/с |

**Где купить VPS (от 100–300 ₽/мес):**
- Timeweb (timeweb.com) — Россия
- Selectel (selectel.ru) — Россия
- Hetzner (hetzner.com) — Европа
- DigitalOcean (digitalocean.com) — глобально

---

## Шаг 1: Подключение по SSH

```bash
# Замените IP на адрес вашего сервера
ssh root@YOUR_SERVER_IP

# Если используете SSH-ключ:
ssh -i ~/.ssh/id_rsa root@YOUR_SERVER_IP
```

---

## Шаг 2: Установка Python 3.11 на Ubuntu 22.04

```bash
# Обновляем систему
apt update && apt upgrade -y

# Устанавливаем Python 3.11
apt install -y python3.11 python3.11-venv python3.11-dev python3-pip

# Проверяем версию
python3.11 --version
# Должно показать: Python 3.11.x

# Устанавливаем git
apt install -y git
```

---

## Шаг 3: Создание пользователя (рекомендуется)

```bash
# Создаём пользователя для бота
useradd -m -s /bin/bash botuser
su - botuser
```

---

## Шаг 4: Клонирование и установка зависимостей

```bash
# Клонируем репозиторий
cd /home/botuser
git clone https://github.com/YOUR_USERNAME/manicure_bot.git
cd manicure_bot

# Создаём виртуальное окружение
python3.11 -m venv venv
source venv/bin/activate

# Устанавливаем зависимости
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Шаг 5: Настройка бота

```bash
# Запускаем интерактивный скрипт настройки
python3 setup_master.py
```

Скрипт задаст вопросы и создаст `.env` и `config.json`.

**Если хотите настроить вручную:**
```bash
cp .env.example .env
nano .env  # Заполните BOT_TOKEN и ADMIN_IDS
nano config.json  # Настройте услуги и тексты
```

---

## Шаг 6: Применение миграций БД

```bash
# Создаём папку для данных
mkdir -p data

# Применяем миграции (если использует скрипт миграции)
python3 -c "
from src.infrastructure.database.connection import DatabaseManager
from src.config.settings import get_settings
settings = get_settings()
db = DatabaseManager(settings.db_path)
db.run_migrations('migrations/')
print('Migrations applied successfully')
"
```

---

## Шаг 7: Тестовый запуск

```bash
source venv/bin/activate
python3 main.py
```

Если видите `Bot started successfully` — всё работает!  
Остановите: `Ctrl+C`

---

## Шаг 8: Настройка systemd (автозапуск)

```bash
# Создаём unit-файл (от root)
exit  # Если зашли под botuser
```

Создайте файл `/etc/systemd/system/manicure_bot.service`:

```ini
[Unit]
Description=Manicure Telegram Bot
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=botuser
WorkingDirectory=/home/botuser/manicure_bot
ExecStart=/home/botuser/manicure_bot/venv/bin/python3 main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Ограничения ресурсов
MemoryMax=512M
CPUQuota=50%

[Install]
WantedBy=multi-user.target
```

```bash
# Создаём файл
nano /etc/systemd/system/manicure_bot.service
# (вставьте содержимое выше)

# Активируем и запускаем
systemctl daemon-reload
systemctl enable manicure_bot
systemctl start manicure_bot
```

---

## Шаг 9: Автозапуск при перезагрузке

```bash
# Проверяем статус
systemctl status manicure_bot

# Должно показать: Active: active (running)

# Тестируем перезагрузку
reboot

# После перезагрузки подключаемся и проверяем
ssh root@YOUR_SERVER_IP
systemctl status manicure_bot
```

---

## Просмотр логов

```bash
# Последние 50 строк лога
journalctl -u manicure_bot -n 50

# Следить за логами в реальном времени
journalctl -u manicure_bot -f

# Логи за последний час
journalctl -u manicure_bot --since "1 hour ago"
```

---

## Обновление бота

```bash
cd /home/botuser/manicure_bot
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
systemctl restart manicure_bot
```

---

## Частые ошибки и решения

### ❌ `ModuleNotFoundError: No module named 'aiogram'`
```bash
source venv/bin/activate
pip install -r requirements.txt
```

### ❌ `[Errno 2] No such file or directory: 'data/manicure_bot.db'`
```bash
mkdir -p data
```

### ❌ `Unauthorized` при запуске
- Проверьте BOT_TOKEN в `.env`
- Убедитесь что токен не скопирован с пробелами

### ❌ `ADMIN_IDS не настроены`
- Найдите ваш Telegram ID: напишите @userinfobot
- Добавьте в `.env`: `ADMIN_IDS=ваш_id`

### ❌ Бот не отвечает после запуска
```bash
# Проверяем ошибки
journalctl -u manicure_bot -n 100 --no-pager

# Тестируем запуск вручную
cd /home/botuser/manicure_bot
source venv/bin/activate
python3 main.py
```

### ❌ `Permission denied` для файлов
```bash
chown -R botuser:botuser /home/botuser/manicure_bot
chmod -R 755 /home/botuser/manicure_bot
```

### ❌ Бот не получает обновления (webhook конфликт)
```bash
# Сбрасываем webhook (если был настроен ранее)
curl "https://api.telegram.org/botYOUR_TOKEN/deleteWebhook"
```

---

## Бэкап данных

Бот автоматически создаёт бэкапы в `data/backups/` каждый день в 2:00.

Ручной бэкап:
```bash
cp data/manicure_bot.db data/backups/manual_backup_$(date +%Y%m%d).db
```
