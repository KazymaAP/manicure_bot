#!/bin/bash
# setup.sh — Автоматическая настройка виртуального окружения и первый запуск
# Использование: bash setup.sh

set -e

echo "🌸 Manicure Bot — Автоматическая установка"
echo "============================================"

# ── 1. Проверка Python ────────────────────────────────────────────────────────
PYTHON_MIN="3.10"
PYTHON_CMD=""

for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -gt 3 ] || ([ "$major" -eq 3 ] && [ "$minor" -ge 10 ]); then
            PYTHON_CMD="$cmd"
            echo "✅ Python $version найден: $cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "❌ Ошибка: Python $PYTHON_MIN+ не найден."
    echo "   Установите: sudo apt install python3 python3-pip python3-venv"
    exit 1
fi

# ── 2. Создание виртуального окружения ───────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo "📦 Создание виртуального окружения .venv..."
    "$PYTHON_CMD" -m venv .venv
    echo "✅ Виртуальное окружение создано"
else
    echo "ℹ️  Виртуальное окружение .venv уже существует"
fi

# ── 3. Активация и установка зависимостей ────────────────────────────────────
echo "📦 Установка зависимостей..."
.venv/bin/pip install --upgrade pip --quiet

# Сначала устанавливаем aiogram и pydantic-settings с явными версиями
.venv/bin/pip install aiogram==3.13.1 pydantic-settings==2.7.0 --quiet

# Затем остальные зависимости
.venv/bin/pip install -r requirements.txt --quiet

echo "✅ Зависимости установлены"

# ── 4. Настройка .env ─────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    echo ""
    echo "⚙️  Создание .env из примера..."
    cp .env.example .env
    echo ""
    echo "📝 ВАЖНО: Отредактируйте файл .env и укажите:"
    echo "   BOT_TOKEN  — токен от @BotFather"
    echo "   ADMIN_IDS  — ваш Telegram ID (узнать у @userinfobot)"
    echo ""
    echo "   Команда: nano .env"
    echo ""
    read -p "Открыть .env для редактирования сейчас? [y/N] " answer
    if [ "$answer" = "y" ] || [ "$answer" = "Y" ]; then
        ${EDITOR:-nano} .env
    fi
else
    echo "ℹ️  .env уже существует, пропускаем"
fi

# ── 5. Создание директории для данных ────────────────────────────────────────
mkdir -p data
echo "✅ Директория data/ готова"

# ── 6. Проверка конфигурации ─────────────────────────────────────────────────
echo ""
echo "🔍 Проверка конфигурации..."
if .venv/bin/python -c "from src.config.settings import get_settings; get_settings()" 2>/dev/null; then
    echo "✅ Конфигурация валидна"
else
    echo "⚠️  Проверьте настройки в .env (BOT_TOKEN и ADMIN_IDS обязательны)"
fi

# ── 7. Итог ──────────────────────────────────────────────────────────────────
echo ""
echo "🎉 Установка завершена!"
echo ""
echo "Для запуска бота:"
echo "  source .venv/bin/activate"
echo "  python main.py"
echo ""
echo "Или через Docker:"
echo "  docker-compose up -d"
echo ""
echo "Подробная документация: INSTALL.md"
