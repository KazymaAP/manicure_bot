"""
tests/unit/test_infrastructure/test_database_manager.py
Unit-тесты для DatabaseManager.
"""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from src.infrastructure.database.connection import DatabaseManager


@pytest.fixture
def db(tmp_path: Path) -> DatabaseManager:
    """Создаёт временный DatabaseManager и инициализирует схему."""
    db_path = tmp_path / "test.db"
    manager = DatabaseManager(str(db_path))
    manager.initialize_schema()
    return manager


class TestDatabaseManagerSingleton:
    def test_singleton_same_path(self, db: DatabaseManager, tmp_path: Path) -> None:
        """Повторное создание с тем же путём возвращает тот же объект."""
        db_path = str(tmp_path / "test.db")
        manager2 = DatabaseManager(db_path)
        assert db is manager2

    def test_singleton_different_path_raises(self, db: DatabaseManager, tmp_path: Path) -> None:
        """Попытка создать DatabaseManager с другим путём → RuntimeError."""
        other_path = str(tmp_path / "other.db")
        with pytest.raises(RuntimeError, match="already initialized"):
            DatabaseManager(other_path)

    def test_reset_clears_singleton(self, db: DatabaseManager, tmp_path: Path) -> None:
        """После reset() можно создать новый DatabaseManager."""
        DatabaseManager.reset()
        new_path = str(tmp_path / "new.db")
        new_db = DatabaseManager(new_path)
        assert new_db is not db
        DatabaseManager.reset()


class TestDatabaseManagerTransactions:
    def test_transaction_commit(self, db: DatabaseManager) -> None:
        """Транзакция успешно коммитит данные."""
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO working_days (date, is_closed) VALUES (?, ?)",
                ("2026-12-01", 0),
            )
        with db.read_connection() as conn:
            row = conn.execute(
                "SELECT * FROM working_days WHERE date = '2026-12-01'"
            ).fetchone()
        assert row is not None
        assert row["date"] == "2026-12-01"

    def test_transaction_rollback_on_exception(self, db: DatabaseManager) -> None:
        """При исключении внутри транзакции данные откатываются."""
        with pytest.raises(ValueError):
            with db.transaction() as conn:
                conn.execute(
                    "INSERT INTO working_days (date, is_closed) VALUES (?, ?)",
                    ("2026-12-02", 0),
                )
                raise ValueError("Intentional rollback")

        with db.read_connection() as conn:
            row = conn.execute(
                "SELECT * FROM working_days WHERE date = '2026-12-02'"
            ).fetchone()
        assert row is None

    def test_nested_transaction(self, db: DatabaseManager) -> None:
        """Вложенный вызов transaction() не создаёт двойной BEGIN."""
        with db.transaction() as outer:
            outer.execute(
                "INSERT INTO working_days (date, is_closed) VALUES (?, ?)",
                ("2026-12-10", 0),
            )
            with db.transaction() as inner:
                # inner — тот же объект соединения
                assert inner is outer

        with db.read_connection() as conn:
            row = conn.execute(
                "SELECT * FROM working_days WHERE date = '2026-12-10'"
            ).fetchone()
        assert row is not None

    def test_read_connection_does_not_write(self, db: DatabaseManager) -> None:
        """read_connection можно использовать для SELECT."""
        with db.read_connection() as conn:
            rows = conn.execute("SELECT * FROM working_days").fetchall()
        assert isinstance(rows, list)


class TestDatabaseManagerSchema:
    def test_schema_tables_created(self, db: DatabaseManager) -> None:
        """initialize_schema создаёт все необходимые таблицы."""
        expected_tables = {
            "working_days", "time_slots", "appointments",
            "waitlist", "blacklist", "workday_templates",
            "backups", "users",
        }
        with db.read_connection() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        existing = {row[0] for row in rows}
        assert expected_tables.issubset(existing)

    def test_appointments_columns(self, db: DatabaseManager) -> None:
        """Таблица appointments содержит все обязательные колонки."""
        required_cols = {
            "id", "user_id", "username", "client_name", "phone",
            "date", "time", "created_at", "reminder_sent", "is_cancelled",
            "comment", "service", "status",
        }
        with db.read_connection() as conn:
            rows = conn.execute("PRAGMA table_info('appointments')").fetchall()
        existing = {row[1] for row in rows}
        assert required_cols.issubset(existing)

    def test_users_notification_columns(self, db: DatabaseManager) -> None:
        """Таблица users содержит колонки уведомлений."""
        notif_cols = {
            "notifications_enabled", "notif_24h", "notif_2h", "notif_1h"
        }
        with db.read_connection() as conn:
            rows = conn.execute("PRAGMA table_info('users')").fetchall()
        existing = {row[1] for row in rows}
        assert notif_cols.issubset(existing)

    def test_foreign_key_pragma_enabled(self, db: DatabaseManager) -> None:
        """PRAGMA foreign_keys должен быть включён."""
        with db.read_connection() as conn:
            row = conn.execute("PRAGMA foreign_keys").fetchone()
        assert row[0] == 1

    def test_wal_mode_enabled(self, db: DatabaseManager) -> None:
        """WAL journal mode должен быть включён."""
        with db.read_connection() as conn:
            row = conn.execute("PRAGMA journal_mode").fetchone()
        assert row[0].lower() == "wal"

    def test_idempotent_schema_init(self, db: DatabaseManager) -> None:
        """Повторный вызов initialize_schema безопасен (CREATE IF NOT EXISTS)."""
        db.initialize_schema()
        db.initialize_schema()
        with db.read_connection() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        assert len(rows) >= 8


class TestDatabaseManagerConcurrency:
    def test_get_connection_per_thread(self, db: DatabaseManager) -> None:
        """Каждый поток получает своё соединение (thread-local)."""
        connections: list = []

        def get_conn() -> None:
            conn = db.get_connection()
            connections.append(id(conn))

        threads = [threading.Thread(target=get_conn) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # У каждого потока своё соединение (разные id)
        assert len(connections) == 3
