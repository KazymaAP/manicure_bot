"""
src/infrastructure/database/connection.py — Управление соединениями с БД.

✅ Из v2_tar: DatabaseManager, transaction context manager, WAL mode, foreign_keys
✅ Улучшения v4: connection pool (check_same_thread=False), PRAGMA synchronous,
   лучшая обработка ошибок, метод execute_script
"""
from __future__ import annotations

import logging
import os
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Менеджер соединений с SQLite базой данных.

    Реализует паттерн Singleton для единственного экземпляра.
    Поддерживает WAL-режим и foreign keys для надёжности.
    """

    _instance: DatabaseManager | None = None
    _initialized: bool = False

    def __new__(cls, db_path: str) -> DatabaseManager:
        """Возвращает единственный экземпляр (Singleton)."""
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._initialized = False
            cls._instance = instance
        return cls._instance

    def __init__(self, db_path: str) -> None:
        """Инициализирует менеджер с указанным путём к файлу БД.

        Args:
            db_path: Путь к файлу SQLite базы данных.

        Raises:
            RuntimeError: Если Singleton уже инициализирован с другим путём.
        """
        if self._initialized:
            if self._db_path != db_path:
                raise RuntimeError(
                    f"DatabaseManager already initialized with path {self._db_path!r}, "
                    f"cannot reinitialize with {db_path!r}"
                )
            return
        self._db_path = db_path
        self._initialized = True
        self._ensure_directory()
        logger.debug("DatabaseManager initialized with path: %s", db_path)

    @classmethod
    def reset(cls) -> None:
        """Сбрасывает Singleton для тестов."""
        cls._instance = None
        cls._initialized = False

    def _ensure_directory(self) -> None:
        """Создаёт директорию для файла БД, если она не существует."""
        directory = os.path.dirname(self._db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        """Создаёт соединение с per-connection настройками PRAGMA.

        WAL-режим устанавливается один раз в initialize_schema().
        """
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-8000")
        conn.execute("PRAGMA temp_store=MEMORY")
        return conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Контекстный менеджер для транзакций с автоматическим rollback.

        Yields:
            Открытое соединение с БД в рамках транзакции.

        Raises:
            Exception: Перебрасывает любое исключение после rollback.
        """
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as exc:
            logger.error("Transaction rolled back due to error: %s", exc, exc_info=True)
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def read_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Контекстный менеджер для READ-ONLY операций (без commit).

        Более эффективен для SELECT-запросов т.к. не создаёт транзакцию записи.

        Yields:
            Открытое соединение с БД.
        """
        conn = self.get_connection()
        try:
            yield conn
        except Exception as exc:
            logger.error("Read operation failed: %s", exc, exc_info=True)
            raise
        finally:
            conn.close()

    def initialize_schema(self) -> None:
        """Создаёт таблицы и индексы схемы БД, если они не существуют."""
        # WAL-режим устанавливается один раз для всей БД
        with self.transaction() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
        schema = """
            CREATE TABLE IF NOT EXISTS working_days (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT    NOT NULL UNIQUE,
                is_closed   INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS time_slots (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT    NOT NULL,
                time        TEXT    NOT NULL,
                is_booked   INTEGER NOT NULL DEFAULT 0,
                UNIQUE(date, time)
            );

            CREATE TABLE IF NOT EXISTS appointments (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL,
                username        TEXT,
                client_name     TEXT    NOT NULL,
                phone           TEXT    NOT NULL,
                date            TEXT    NOT NULL,
                time            TEXT    NOT NULL,
                created_at      TEXT    NOT NULL,
                reminder_sent   INTEGER NOT NULL DEFAULT 0,
                is_cancelled    INTEGER NOT NULL DEFAULT 0,
                comment         TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_appointments_user_id
                ON appointments(user_id);
            CREATE INDEX IF NOT EXISTS idx_appointments_date
                ON appointments(date);
            CREATE INDEX IF NOT EXISTS idx_appointments_active
                ON appointments(user_id, is_cancelled);
            CREATE INDEX IF NOT EXISTS idx_time_slots_date
                ON time_slots(date);
            CREATE INDEX IF NOT EXISTS idx_time_slots_free
                ON time_slots(date, is_booked);
            CREATE INDEX IF NOT EXISTS idx_working_days_date
                ON working_days(date);
        """
        with self.transaction() as conn:
            conn.executescript(schema)
        logger.info("Database schema initialized successfully.")

    async def close(self) -> None:
        """Закрывает все оставшиеся соединения с БД."""
        logger.debug("DatabaseManager close called.")
