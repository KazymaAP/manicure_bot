"""
tests/conftest.py — Общие фикстуры для всех тестов.

Обеспечивает:
- Автоматический сброс DatabaseManager Singleton между тестами
- Общие мок-фикстуры для репозиториев и сервисов
- Конфигурацию pytest-asyncio
"""
from __future__ import annotations

import pytest

from src.infrastructure.database.connection import DatabaseManager


@pytest.fixture(autouse=True)
def reset_db_singleton():
    """Автоматически сбрасывает Singleton DatabaseManager между тестами.

    Без этого Singleton остаётся живым после первого теста с реальной БД,
    что вызывает RuntimeError при попытке переинициализации с другим db_path.

    autouse=True гарантирует выполнение для каждого теста в пакете.
    """
    DatabaseManager.reset()
    yield
    DatabaseManager.reset()
