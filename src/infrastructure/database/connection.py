"""
src/infrastructure/database/connection.py — Управление соединениями с БД.

✅ Из v2_tar: DatabaseManager, transaction context manager, WAL mode, foreign_keys
✅ Улучшения v4: connection pool (check_same_thread=False), PRAGMA synchronous,
   лучшая обработка ошибок, метод execute_script
✅ Улучшения v5: per-thread connection reuse, thread-local storage
✅ FIXED BUG-07: WAL-режим устанавливается в get_connection() для каждого нового соединения
✅ FIXED BUG-01: reset() корректно закрывает ВСЕ зарегистрированные соединения
"""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Менеджер соединений с SQLite базой данных.

    FIXED: Сделана потокобезопасная Singleton-инициализация с lock,
    убрано закрытие соединения внутри transaction/read_connection (перепользование per-thread),
    close() теперь закрывает соединение текущего потока.
    """

    _instance: DatabaseManager | None = None
    _initialized: bool = False
    _thread_local = threading.local()
    _lock = threading.RLock()  # FIXED: блокировка для потокобезопасного создания/сброса

    def __new__(cls, db_path: str) -> DatabaseManager:
        """Потокобезопасный Singleton: возвращает единственный экземпляр."""
        with cls._lock:  # FIXED: синхронизация создания
            if cls._instance is None:
                instance = super().__new__(cls)
                instance._initialized = False
                cls._instance = instance
            return cls._instance

    def __init__(self, db_path: str) -> None:
        """Инициализирует менеджер с путём к файлу БД.

        Повторные инициализации с тем же путём безопасны; с другим путём — ошибка.

        FIXED: добавлен реестр открытых соединений (self._connections) и блокировка
        для возможности корректного закрытия всех соединений при shutdown/reset.
        """
        if self._initialized:
            if self._db_path != db_path:
                raise RuntimeError(
                    f"DatabaseManager already initialized with path {self._db_path!r}, cannot reinitialize with {db_path!r}"
                )
            return
        self._db_path = db_path
        self._initialized = True
        self._ensure_directory()
        # Регистр всех соединений: thread_id -> sqlite3.Connection
        self._connections: dict[int, sqlite3.Connection] = {}
        self._connections_lock = threading.RLock()
        logger.debug("DatabaseManager initialized with path: %s", db_path)

    @classmethod
    def reset(cls) -> None:
        """Сбрасывает Singleton для тестов — закрывает ВСЕ зарегистрированные соединения.

        FIXED BUG-01: потокобезопасный reset с блокировкой. Закрывает все соединения из
        реестра _connections (не только текущего потока), что важно для корректной очистки
        в тестах между тест-кейсами. Вызывайте в teardown каждого теста.
        """
        with cls._lock:
            try:
                # Закрываем все зарегистрированные соединения (не только текущего потока)
                instance = cls._instance
                if instance is not None:
                    connections_lock = getattr(instance, '_connections_lock', None)
                    connections = getattr(instance, '_connections', {})
                    if connections_lock:
                        with connections_lock:
                            for tid, conn in list(connections.items()):
                                try:
                                    conn.close()
                                except Exception:
                                    pass
                            connections.clear()
                # Очищаем thread-local соединение текущего потока
                try:
                    if hasattr(cls._thread_local, 'conn') and cls._thread_local.conn:
                        try:
                            cls._thread_local.conn.close()
                        except Exception:
                            pass
                        cls._thread_local.conn = None
                except Exception:
                    pass
            finally:
                # FIXED CRIT-03: явно сбрасываем instance._initialized, иначе instance-атрибут
                # остаётся True даже после cls._initialized = False и следующая инициализация
                # с тем же/другим путём пропустит __init__ из-за проверки self._initialized.
                if instance is not None:
                    try:
                        instance._initialized = False
                    except Exception:
                        pass
                cls._instance = None
                cls._initialized = False

    def _ensure_directory(self) -> None:
        """Создаёт директорию для файла БД, если она не существует."""
        directory = os.path.dirname(self._db_path)
        if not directory:
            return
        try:
            os.makedirs(directory, exist_ok=True)
            test_file = os.path.join(directory, ".write_test")
            with open(test_file, "w") as f:
                f.write("")
            os.remove(test_file)
        except (OSError, IOError) as e:
            raise RuntimeError(
                f"Cannot create or write to database directory {directory!r}: {e}. Check directory permissions and volume mounts (Docker)."
            ) from e

    def get_connection(self) -> sqlite3.Connection:
        """Создаёт или переиспользует соединение для текущего потока (per-thread reuse).

        FIXED: не закрываем соединение автоматически — управление жизненным циклом перенесено в close()/reset().
        FIXED: регистрируем соединение в self._connections для правильного закрытия при shutdown.
        """
        if not hasattr(self._thread_local, 'conn') or self._thread_local.conn is None:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            # FIXED BUG-07: WAL-режим устанавливается для каждого нового соединения,
            # а не только в initialize_schema(). SQLite WAL глобален для файла, но
            # явная установка в каждом потоке — надёжная практика.
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-8000")
            conn.execute("PRAGMA temp_store=MEMORY")
            self._thread_local.conn = conn
            # FIXED: регистрируем соединение в реестре для полного отслеживания
            thread_id = threading.get_ident()
            with self._connections_lock:
                self._connections[thread_id] = conn
        return self._thread_local.conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Контекстный менеджер для транзакций.

        FIXED: поддержка вложенных транзакций — если транзакция уже активна,
        просто возвращаем соединение без начинания новой (аналог SAVEPOINT).
        FIXED: используем conn.in_transaction вместо isolation_level (более надёжно).
        """
        conn = self.get_connection()
        in_transaction = False
        try:
            # Проверяем есть ли уже активная транзакция
            # in_transaction — стандартный способ для Python 3.2+
            if hasattr(conn, 'in_transaction') and conn.in_transaction:
                # Уже в транзакции, просто возвращаем соединение
                yield conn
            else:
                # Начинаем явную транзакцию с блокировкой записи (atomicity across operations)
                conn.execute("BEGIN IMMEDIATE")  # FIXED: избежать гонки при конкурентном бронировании
                in_transaction = True
                yield conn
                conn.commit()
        except Exception as exc:
            logger.error("Transaction rolled back due to error: %s", exc, exc_info=True)
            if in_transaction:
                try:
                    conn.rollback()
                except Exception:
                    logger.exception("Rollback failed")
            raise

    @contextmanager
    def read_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Контекстный менеджер для READ-ONLY операций (без commit/close).

        FIXED: не закрываем соединение — это важно при переиспользовании per-thread.
        """
        conn = self.get_connection()
        try:
            yield conn
        except Exception as exc:
            logger.error("Read operation failed: %s", exc, exc_info=True)
            raise

    def initialize_schema(self) -> None:
        """Создаёт таблицы и индексы схемы БД, если они не существуют.

        FIXED H-06: executescript() всегда вызывает неявный COMMIT перед первым SQL-запросом.
        Поэтому вызов executescript() внутри transaction() нарушает управление транзакцией.
        Решение: вызываем executescript() НАПРЯМУЮ на соединении, без BEGIN/COMMIT обёртки.
        """
        # FIXED: WAL-режим устанавливается ВНЕ транзакции — нельзя менять journal_mode внутри BEGIN
        conn = self.get_connection()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.commit()
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
                UNIQUE(date, time),
                -- FIXED BUG-C3: добавлен FOREIGN KEY для каскадного удаления слотов при удалении дня
                FOREIGN KEY (date) REFERENCES working_days(date) ON DELETE CASCADE
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
                comment         TEXT,
                service         TEXT DEFAULT NULL,
                status          INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_appointments_user_id
                ON appointments(user_id);
            CREATE INDEX IF NOT EXISTS idx_appointments_date
                ON appointments(date);
            CREATE INDEX IF NOT EXISTS idx_appointments_active
                ON appointments(user_id, is_cancelled);
            CREATE INDEX IF NOT EXISTS idx_appointments_date_active
                ON appointments(date, is_cancelled);
            CREATE INDEX IF NOT EXISTS idx_time_slots_date
                ON time_slots(date);
            CREATE INDEX IF NOT EXISTS idx_time_slots_free
                ON time_slots(date, is_booked);
            CREATE INDEX IF NOT EXISTS idx_working_days_date
                ON working_days(date);

            CREATE TABLE IF NOT EXISTS waitlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, date)
            );

            -- FIXED: Добавлены таблицы для админ-функций: blacklist и шаблоны рабочих дней
            CREATE TABLE IF NOT EXISTS blacklist (
                user_id INTEGER PRIMARY KEY,
                reason TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS workday_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                slots TEXT NOT NULL, -- JSON-encoded список ['09:00','10:00']
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            -- FIXED: таблица бэкапов для учета резервных копий (метаданные)
            CREATE TABLE IF NOT EXISTS backups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            -- FIXED: таблица всех пользователей, взаимодействовавших с ботом
            -- Используется для рассылки всем пользователям, а не только с активными записями
            -- FIXED BUG-09: добавлена колонка notifications_enabled для управления уведомлениями
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                notifications_enabled INTEGER NOT NULL DEFAULT 1,
                notif_24h INTEGER NOT NULL DEFAULT 1,
                notif_2h INTEGER NOT NULL DEFAULT 1,
                notif_1h INTEGER NOT NULL DEFAULT 1
            );
        """
        # FIXED H-06: executescript() вызывается НАПРЯМУЮ (не внутри transaction()),
        # т.к. executescript() сам делает неявный COMMIT перед выполнением DDL-команд.
        # Вызов внутри BEGIN IMMEDIATE нарушил бы управление транзакцией.
        conn.executescript(schema)
        # Обратная совместимость: добавляем отсутствующие колонки appointments
        try:
            with self.transaction() as conn2:
                cols = [r[1] for r in conn2.execute("PRAGMA table_info('appointments')").fetchall()]
                for col_name, col_def in [
                    ("service", "TEXT DEFAULT NULL"),
                    ("status", "INTEGER NOT NULL DEFAULT 0"),
                ]:
                    if col_name not in cols:
                        conn2.execute(f"ALTER TABLE appointments ADD COLUMN {col_name} {col_def}")
                        logger.info("Added missing column '%s' to appointments table.", col_name)
                # Синхронизируем status с is_cancelled для существующих записей
                if "status" not in cols:
                    conn2.execute("UPDATE appointments SET status = is_cancelled WHERE status = 0")
                    logger.info("Synchronized 'status' column from 'is_cancelled' for existing records.")
        except Exception:
            logger.exception("Failed to ensure columns in appointments table; continuing.")
        # Обратная совместимость: добавляем колонки уведомлений в users
        try:
            with self.transaction() as conn2:
                user_cols = [r[1] for r in conn2.execute("PRAGMA table_info('users')").fetchall()]
                for col_name, col_def in [
                    ("notifications_enabled", "INTEGER NOT NULL DEFAULT 1"),
                    ("notif_24h", "INTEGER NOT NULL DEFAULT 1"),
                    ("notif_2h", "INTEGER NOT NULL DEFAULT 1"),
                    ("notif_1h", "INTEGER NOT NULL DEFAULT 1"),
                ]:
                    if col_name not in user_cols:
                        conn2.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}")
                        logger.info("Added missing column '%s' to users table.", col_name)
        except Exception:
            logger.exception("Failed to ensure notification columns in users table; continuing.")
        logger.info("Database schema initialized successfully.")

    async def close(self) -> None:
        """Закрывает все соединения, известные менеджеру.

        FIXED: ранее метод закрывал только соединение текущего потока. Теперь: закрываем
        все зарегистрированные соединения, очищаем реестр и освобождаем ресурсы.
        """
        logger.debug("DatabaseManager.close called. Closing all registered connections.")
        try:
            # Закрываем все соединения, зарегистрированные в экземпляре
            with getattr(self, '_connections_lock', threading.RLock()):
                for tid, conn in list(getattr(self, '_connections', {}).items()):
                    try:
                        conn.close()
                    except Exception:
                        logger.exception("Error closing DB connection for thread %s", tid)
                self._connections.clear()
            # Также очистим thread-local указатель для текущего потока
            try:
                if hasattr(self._thread_local, 'conn'):
                    self._thread_local.conn = None
            except Exception:
                pass
        except Exception:
            logger.exception("Unexpected error during DatabaseManager.close()")
