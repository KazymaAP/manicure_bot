#!/usr/bin/env python3
"""
setup_master.py — Интерактивный скрипт настройки бота для нового мастера.

Задаёт вопросы на русском языке, проверяет BOT_TOKEN через Telegram API,
и автоматически генерирует .env и config.json.

Использование:
    python3 setup_master.py
"""

import json
import os
import sys
import urllib.error
import urllib.request


def print_header():
    print("\n" + "="*60)
    print("     🌸  НАСТРОЙКА БОТА ДЛЯ ЗАПИСИ НА МАНИКЮР  🌸")
    print("="*60)
    print("Этот скрипт поможет настроить бота под вашу студию.")
    print("Отвечайте на вопросы и нажимайте Enter.\n")


def ask(prompt: str, default: str = "", required: bool = True) -> str:
    """Запрашивает ввод у пользователя."""
    # SIM108 FIX: тернарный оператор вместо if/else блока
    full_prompt = f"{prompt} [{default}]: " if default else f"{prompt}: "

    while True:
        value = input(full_prompt).strip()
        if not value and default:
            return default
        if not value and required:
            print("  ❌ Это поле обязательно. Попробуйте ещё раз.")
            continue
        return value


def ask_yn(prompt: str, default: bool = True) -> bool:
    """Задаёт вопрос да/нет."""
    hint = "[Да/нет]" if default else "[да/Нет]"
    answer = input(f"{prompt} {hint}: ").strip().lower()
    if not answer:
        return default
    return answer in ("д", "да", "y", "yes", "1")


def validate_bot_token(token: str) -> tuple[bool, str]:
    """Проверяет BOT_TOKEN через Telegram API getMe."""
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
            if data.get("ok"):
                bot = data["result"]
                username = bot.get("username", "")
                name = bot.get("first_name", "")
                return True, f"@{username} ({name})"
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, "Неверный токен (401 Unauthorized)"
    except Exception as e:
        return False, f"Ошибка соединения: {e}"
    return False, "Неизвестная ошибка"


def parse_services(services_input: str) -> dict:
    """Парсит строку услуг формата 'Маникюр:1500:60,Педикюр:2000:90'."""
    services = {}
    for item in services_input.split(","):
        item = item.strip()
        if not item:
            continue
        parts = item.split(":")
        if len(parts) >= 1:
            name = parts[0].strip()
            price = int(parts[1].strip()) if len(parts) > 1 and parts[1].strip().isdigit() else 0
            duration = int(parts[2].strip()) if len(parts) > 2 and parts[2].strip().isdigit() else 60
            if name:
                services[name] = {"price": price, "duration": duration}
    return services


def main():
    print_header()

    # ── Шаг 1: Токен бота ─────────────────────────────────────────────────
    print("📌 Шаг 1: Токен Telegram-бота")
    print("   Получить токен: @BotFather → /newbot → скопируйте токен\n")

    while True:
        bot_token = ask("  Вставьте BOT_TOKEN")
        print("  🔍 Проверяю токен через Telegram API...")
        ok, info = validate_bot_token(bot_token)
        if ok:
            print(f"  ✅ Токен верный! Бот: {info}")
            break
        else:
            print(f"  ❌ {info}")
            retry = ask_yn("  Попробовать другой токен?", default=True)
            if not retry:
                print("  ⚠️  Продолжаем без проверки токена.")
                break

    # ── Шаг 2: Ваш Telegram ID ────────────────────────────────────────────
    print("\n📌 Шаг 2: Ваш Telegram ID (для доступа к админ-панели)")
    print("   Получить ID: напишите @userinfobot или @getmyid_bot\n")

    while True:
        admin_id_raw = ask("  Ваш Telegram ID (число)")
        if admin_id_raw.strip().lstrip("-").isdigit():
            admin_id = int(admin_id_raw.strip())
            break
        print("  ❌ ID должен быть числом. Например: 123456789")

    # ── Шаг 3: Данные мастера ─────────────────────────────────────────────
    print("\n📌 Шаг 3: Данные мастера")
    master_name = ask("  Ваше имя (как отображается клиентам)", default="Анастасия")
    speciality = ask("  Специализация", default="мастер маникюра и педикюра")
    phone = ask("  Телефон (или пусто)", required=False)
    instagram = ask("  Instagram (например: @master_manicure)", required=False)
    address = ask("  Адрес студии (или пусто)", required=False)

    # ── Шаг 4: Услуги ─────────────────────────────────────────────────────
    print("\n📌 Шаг 4: Услуги и цены")
    print("   Формат: Название:Цена:Минуты")
    print("   Пример: Маникюр:1500:60,Педикюр:2000:90,Гель-лак:500:30")
    print("   (или Enter для стандартного набора)\n")

    services_raw = ask(
        "  Услуги",
        default="Маникюр:1500:60,Педикюр:2000:90,Покрытие гель-лаком:500:30",
        required=False
    )
    services = parse_services(services_raw) if services_raw else {
        "Маникюр": {"price": 1500, "duration": 60},
        "Педикюр": {"price": 2000, "duration": 90},
        "Покрытие гель-лаком": {"price": 500, "duration": 30},
    }

    print(f"\n  ✅ Добавлено услуг: {len(services)}")
    for name, info in services.items():
        print(f"     💅 {name}: {info['price']} ₽, {info['duration']} мин")

    # ── Шаг 5: Расписание ─────────────────────────────────────────────────
    print("\n📌 Шаг 5: Рабочие часы")
    work_start = ask("  Начало работы (HH:MM)", default="09:00")
    work_end = ask("  Конец работы (HH:MM)", default="18:00")

    try:
        start_h = int(work_start.split(":")[0])
        end_h = int(work_end.split(":")[0])
        time_slots = [f"{h:02d}:00" for h in range(start_h, end_h + 1)]
    except Exception:
        time_slots = ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00"]

    # ── Шаг 6: Напоминания ────────────────────────────────────────────────
    print("\n📌 Шаг 6: Напоминания")
    reminder_hours = ask("  За сколько часов напоминать о визите", default="24")
    try:
        reminder_hours_int = int(reminder_hours)
    except ValueError:
        reminder_hours_int = 24

    # ── Шаг 7: Дополнительно ─────────────────────────────────────────────
    print("\n📌 Шаг 7: Дополнительные настройки")
    timezone = ask("  Временная зона", default="Europe/Moscow")
    required_channel = ask("  Канал для обязательной подписки (@channel) — или пусто", required=False)
    portfolio_url = ask("  URL портфолио (Instagram, сайт) — или пусто", required=False)

    # ── Генерация .env ────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("  Генерирую .env...")

    env_content = f"""# Автоматически сгенерировано setup_master.py
# Редактируйте осторожно!

BOT_TOKEN={bot_token}
ADMIN_IDS={admin_id}

# База данных
DB_PATH=data/manicure_bot.db

# Временная зона
TIMEZONE={timezone}

# Напоминания
REMINDER_HOURS_BEFORE={reminder_hours_int}

# Ограничение записей на клиента
MAX_APPOINTMENTS_PER_USER=1
"""

    if required_channel:
        env_content += f"\n# Обязательная подписка на канал\nREQUIRED_CHANNEL={required_channel}\n"

    if portfolio_url:
        env_content += f"\n# Портфолио\nPORTFOLIO_URL={portfolio_url}\n"

    if phone:
        env_content += f"\n# Контакты\nPHONE={phone}\n"

    if instagram:
        env_content += f"INSTAGRAM={instagram}\n"

    if address:
        env_content += f"ADDRESS={address}\n"

    with open(".env", "w", encoding="utf-8") as f:
        f.write(env_content)
    print("  ✅ .env создан!")

    # ── Генерация config.json ─────────────────────────────────────────────
    print("  Генерирую config.json...")

    welcome_text = (
        f"Привет, {{name}}! 🌸\n\n"
        f"Я — {master_name}, {speciality}.\n"
        "Здесь ты можешь записаться ко мне в удобное время — всё просто и быстро 💅\n\n"
        "Выбери, что тебя интересует:"
    )

    after_visit_text = (
        "Спасибо, что была у меня, {name}! 🌷\n\n"
        "Надеюсь, тебе всё понравилось. Буду рада видеть тебя снова!\n"
        "Если хочешь — запишись уже сейчас 😊"
    )

    config = {
        "master": {
            "name": master_name,
            "speciality": speciality,
            "phone": phone or "",
            "instagram": instagram or "",
            "address": address or "",
            "welcome_text": welcome_text,
            "after_visit_text": after_visit_text,
        },
        "bot": {
            "service_name": "маникюр",
            "welcome": welcome_text,
            "help_text": (
                "ℹ️ <b>Справка</b>\n\n"
                "📅 <b>Записаться</b> — выбрать услугу, дату и время\n"
                "📋 <b>Мои записи</b> — посмотреть ваши активные записи\n"
                "💰 <b>Цены</b> — прайс на услуги\n"
                "📞 <b>Связаться с мастером</b> — написать напрямую\n\n"
                "Если что-то не получается — просто напишите сюда 🌸"
            ),
        },
        "schedule": {
            "default_time_slots": time_slots,
            "slot_interval_minutes": 60,
        },
        "notifications": {
            "reminder_hours_before": reminder_hours_int,
        },
        "services": services,
        "prices_title": "💅 <b>Прайс-лист</b>\n\nВсе работы выполняются с любовью и вниманием к деталям 🌸\n\n",
        "prices_footer": "\n<i>По вопросам и записи — нажмите «Связаться с мастером»</i>",
        "contacts_title": "📞 <b>Связаться с мастером</b>\n\nПишите в любое время — отвечу как только смогу 🌸\n\n",
    }

    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print("  ✅ config.json создан!")

    # ── Создание папки data ───────────────────────────────────────────────
    os.makedirs("data", exist_ok=True)
    os.makedirs("data/backups", exist_ok=True)
    print("  ✅ Папки data/ и data/backups/ созданы!")

    # ── Итог ──────────────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("  🎉  НАСТРОЙКА ЗАВЕРШЕНА!")
    print("="*60)
    print("\n📋 Что дальше:")
    print("  1. Установите зависимости: pip install -r requirements.txt")
    print("  2. Запустите бота:         python3 main.py")
    print("  3. Напишите боту в Telegram: /start")
    print("  4. Для управления зайдите в админ-панель: /admin")
    print("\n📖 Подробная инструкция: DEPLOY.md")
    print("📖 Настройка под мастера: CUSTOMIZATION.md")
    print("\n  Удачи! 🌸\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Настройка отменена.")
        sys.exit(0)
