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

    @property
    def db(self) -> DatabaseManager:
        """FIXED HIGH-05: публичное свойство для доступа к DatabaseManager.

        Исключает необходимость обходить инкапсуляцию через getattr(obj, "_db", None).
        Используйте repo.db вместо getattr(repo, "_db", None) для надёжного доступа.
        """
        return self._db
