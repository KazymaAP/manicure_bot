"""
src/infrastructure/repositories/base.py — Базовый класс репозитория.
"""
from __future__ import annotations

from src.infrastructure.database.connection import DatabaseManager


class BaseRepository:
    """Базовый класс для всех репозиториев."""

    def __init__(self, db: DatabaseManager) -> None:
        """Инициализирует репозиторий.

        Args:
            db: Менеджер соединений с БД.
        """
        self._db = db
