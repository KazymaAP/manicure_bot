# ╔══════════════════════════════════════════════════════════════╗
# ║           Makefile для manicure_bot                         ║
# ║   BUG 1.4 FIX + ТРЕБОВАНИЕ К ПРОДАКШН-ГОТОВНОСТИ          ║
# ╚══════════════════════════════════════════════════════════════╝

.PHONY: help install test lint format run clean

# Переменные
PYTHON = python3
PIP = pip
PYTEST = pytest
RUFF = ruff
MYPY = mypy

help: ## Показать справку по командам
	@echo "Доступные команды:"
	@echo "  make install   — Установить все зависимости"
	@echo "  make test      — Установить зависимости и запустить тесты"
	@echo "  make lint      — Проверить код через ruff"
	@echo "  make format    — Форматировать код через ruff"
	@echo "  make typecheck — Проверить типы через mypy"
	@echo "  make run       — Запустить бота"
	@echo "  make clean     — Удалить артефакты сборки"

install: ## Установить все зависимости
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

test: install ## BUG 1.4 FIX: установить зависимости и запустить тесты
	$(PYTEST) tests/ -v

lint: ## Проверить код через ruff (без исправлений)
	$(RUFF) check src/ tests/

format: ## Форматировать код через ruff
	$(RUFF) format src/ tests/
	$(RUFF) check --fix src/ tests/

typecheck: ## Проверить типы через mypy
	$(MYPY) src/ --ignore-missing-imports

run: ## Запустить бота (требует настроенного .env)
	$(PYTHON) main.py

clean: ## Удалить артефакты
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache htmlcov coverage.xml .mypy_cache 2>/dev/null || true
