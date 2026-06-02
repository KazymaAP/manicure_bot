"""
tests/unit/test_infrastructure/test_backup_service.py
Unit-тесты для BackupService.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.application.services.backup_service import BackupService


@pytest.fixture
def real_db(tmp_path: Path) -> Path:
    """Создаёт реальный SQLite-файл для тестирования бэкапов."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, val TEXT)")
    conn.execute("INSERT INTO test VALUES (1, 'hello')")
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def backup_service(tmp_path: Path, real_db: Path) -> BackupService:
    backup_dir = tmp_path / "backups"
    return BackupService(
        db_path=str(real_db),
        backup_dir=str(backup_dir),
        keep_count=3,
    )


class TestBackupServiceCreate:
    def test_create_backup_success(self, backup_service: BackupService) -> None:
        """Бэкап успешно создаётся."""
        result = backup_service.create_backup()
        assert result is not None
        assert Path(result).exists()
        assert Path(result).name.startswith("backup_")

    def test_backup_content_intact(self, backup_service: BackupService) -> None:
        """Бэкап содержит исходные данные."""
        backup_path = backup_service.create_backup()
        conn = sqlite3.connect(backup_path)
        rows = conn.execute("SELECT * FROM test").fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0][1] == "hello"

    def test_create_backup_missing_db(self, tmp_path: Path) -> None:
        """Если исходная БД не существует — возвращает None."""
        svc = BackupService(
            db_path=str(tmp_path / "nonexistent.db"),
            backup_dir=str(tmp_path / "backups"),
            keep_count=3,
        )
        result = svc.create_backup()
        assert result is None

    def test_backup_creates_directory(self, tmp_path: Path, real_db: Path) -> None:
        """Директория для бэкапов создаётся автоматически."""
        new_backup_dir = tmp_path / "new_backups" / "nested"
        svc = BackupService(
            db_path=str(real_db),
            backup_dir=str(new_backup_dir),
            keep_count=3,
        )
        result = svc.create_backup()
        assert result is not None
        assert new_backup_dir.exists()


class TestBackupServiceRotation:
    def test_rotation_keeps_max_count(self, backup_service: BackupService) -> None:
        """После создания > keep_count бэкапов старые удаляются."""
        for _ in range(5):
            backup_service.create_backup()

        backups = backup_service.get_backup_list()
        assert len(backups) <= backup_service.keep_count

    def test_rotation_keeps_newest(self, backup_service: BackupService) -> None:
        """Ротация сохраняет самые новые файлы."""
        paths = []
        for _ in range(4):
            path = backup_service.create_backup()
            if path:
                paths.append(Path(path).name)

        remaining = backup_service.get_backup_list()
        # Последние 3 должны остаться
        for name in paths[-3:]:
            assert name in remaining

    def test_get_backup_list_sorted(self, backup_service: BackupService) -> None:
        """Список бэкапов отсортирован (новые первыми)."""
        for _ in range(3):
            backup_service.create_backup()

        backups = backup_service.get_backup_list()
        assert backups == sorted(backups, reverse=True)

    def test_keep_count_minimum_one(self, tmp_path: Path, real_db: Path) -> None:
        """keep_count не может быть меньше 1."""
        svc = BackupService(
            db_path=str(real_db),
            backup_dir=str(tmp_path / "backups"),
            keep_count=0,  # должно стать 1
        )
        assert svc.keep_count == 1

    def test_get_backup_list_empty(self, backup_service: BackupService) -> None:
        """Список бэкапов пустой когда нет файлов."""
        backups = backup_service.get_backup_list()
        assert isinstance(backups, list)
