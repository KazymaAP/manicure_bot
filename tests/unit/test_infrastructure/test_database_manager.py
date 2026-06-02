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
    """Создаёт временный DatabaseManager."""
    db_path = tmp_path / "test.db"
    manager = DatabaseManager(str(db_path))
    manager.initialize_schema()
    return manager


class TestDatabaseManager:
    def test_singleton_same_path(self, db: DatabaseManager, tmp_path: Path) -> None:
        """DatabaseManager — Singleton: повторное создание с тем же путём возвращает тот же объект."""
        db_path = str(tmp_path / "test.db")
        manager2 = DatabaseManager(db_path)
        assert db is manager2

    def test_singleton_different_path_raises(self, db: DatabaseManager, tmp_path: Path) -> None:
        """Попытка создать DatabaseManager с другим путём вызывает RuntimeError."""
        other_path = str(tmp_path / "other.db")
        with pytest.raises(RuntimeError, match="already initialized"):
            DatabaseManager(other_path)

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

    def test_transaction_rollback_on_exception(self, db: DatabaseManager) -> None:
        """При исключении внутри транзакции данные откатываются."""
        with pytest.raises(ValueError):
            with db.transaction() as conn:
                conn.execute(
                    "INSERT INTO working_days (date, is_closed) VALUES (?, ?)",
                    ("2026-12-02", 0),
                )
                raise ValueError("Intentional error for rollback test")

        with db.read_connection() as conn:
            row = conn.execute(
                "SELECT * FROM working_days WHERE date = '2026-12-02'"
            ).fetchone()
        assert row is None

    def test_read_connection_no_side_effects(self, db: DatabaseManager) -> None:
        """read_connection не создаёт/изменяет данные."""
        with db.read_connection() as conn:
            rows = conn.execute("SELECT * FROM working_days").fetchall()
        assert isinstance(rows, list)

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

    def test_reset_clears_singleton(self, db: DatabaseManager, tmp_path: Path) -> None:
        """После reset() можно создать новый DatabaseManager."""
        DatabaseManager.reset()
        new_path = str(tmp_path / "new.db")
        new_db = DatabaseManager(new_path)
        assert new_db is not db
        DatabaseManager.reset()
