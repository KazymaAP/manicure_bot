"""
tests/unit/test_infrastructure/test_backup_service.py
Unit-тесты для BackupService.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from src.application.services.backup_service import BackupService


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Создаёт временную SQLite БД для тестов."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, val TEXT)")
    conn.execute("INSERT INTO test VALUES (1, 'hello')")
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def backup_service(temp_db: Path, tmp_path: Path) -> BackupService:
    backup_dir = tmp_path / "backups"
    return BackupService(
        db_path=str(temp_db),
        backup_dir=str(backup_dir),
        keep_count=3,
    )


class TestBackupService:
    def test_create_backup_creates_file(self, backup_service: BackupService) -> None:
        """Бэкап создаёт файл на диске."""
        result = backup_service.create_backup()
        assert result is not None
        assert Path(result).exists()

    def test_backup_file_is_valid_sqlite(self, backup_service: BackupService) -> None:
        """Бэкап является корректной SQLite базой данных."""
        result = backup_service.create_backup()
        assert result is not None
        conn = sqlite3.connect(result)
        rows = conn.execute("SELECT * FROM test").fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0][1] == "hello"

    def test_rotation_keeps_only_n_backups(self, backup_service: BackupService) -> None:
        """Ротация удаляет лишние бэкапы, оставляя только keep_count."""
        for _ in range(5):
            backup_service.create_backup()
        backup_list = backup_service.get_backup_list()
        assert len(backup_list) <= backup_service.keep_count

    def test_create_backup_missing_db(self, tmp_path: Path) -> None:
        """Если файл БД не существует — возвращает None."""
        svc = BackupService(
            db_path=str(tmp_path / "nonexistent.db"),
            backup_dir=str(tmp_path / "backups"),
        )
        result = svc.create_backup()
        assert result is None

    def test_get_backup_list_empty(self, tmp_path: Path, temp_db: Path) -> None:
        """Список бэкапов пуст, если бэкапов нет."""
        svc = BackupService(
            db_path=str(temp_db),
            backup_dir=str(tmp_path / "empty_backups"),
        )
        assert svc.get_backup_list() == []
