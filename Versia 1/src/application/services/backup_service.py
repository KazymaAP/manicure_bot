"""
src/application/services/backup_service.py — Сервис автоматического бэкапа БД.

Резервные копии SQLite с ротацией (хранить N последних).
Использует sqlite3.backup() API для безопасного горячего бэкапа (WAL-safe).
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class BackupService:
    """Управляет резервными копиями SQLite базы данных.

    Создаёт timestamped бэкапы с автоматической ротацией.
    Использует sqlite3.Connection.backup() — безопасный метод для WAL-режима.
    """

    def __init__(self, db_path: str, backup_dir: str = "data/backups", keep_count: int = 7) -> None:
        """Инициализирует сервис бэкапа.

        Args:
            db_path: Путь к файлу БД (например, data/manicure_bot.db).
            backup_dir: Директория для сохранения бэкапов.
            keep_count: Сколько последних бэкапов хранить (минимум 1).
        """
        self.db_path = Path(db_path)
        self.backup_dir = Path(backup_dir)
        self.keep_count = max(1, keep_count)
        self._ensure_backup_dir()

    def _ensure_backup_dir(self) -> None:
        """Создаёт директорию для бэкапов, если её нет."""
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            logger.debug("Backup directory ensured: %s", self.backup_dir)
        except OSError as exc:
            logger.error("Failed to create backup directory %s: %s", self.backup_dir, exc)

    def create_backup(self) -> str | None:
        """Создаёт резервную копию БД с ротацией старых файлов.

        Использует sqlite3.backup() API вместо shutil.copy2 для:
        - Корректной обработки WAL-режима
        - Гарантии консистентности даже при активных транзакциях
        - Предотвращения повреждения бэкапа при параллельных записях

        Returns:
            Путь к созданному бэкапу или None при ошибке.
        """
        if not self.db_path.exists():
            logger.warning("Database file not found: %s", self.db_path)
            return None

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"backup_{timestamp}_{self.db_path.name}"
            backup_path = self.backup_dir / backup_name

            # Оба соединения оборачиваются в try/finally для предотвращения утечек.
            # Если src_conn.backup() бросит исключение — dst_conn и src_conn всё равно закроются.
            src_conn = sqlite3.connect(str(self.db_path))
            try:
                dst_conn = sqlite3.connect(str(backup_path))
                try:
                    # sqlite3.backup() корректно обрабатывает WAL и гарантирует консистентность
                    src_conn.backup(dst_conn)
                    logger.info("Backup created: %s", backup_path)
                finally:
                    dst_conn.close()
            finally:
                src_conn.close()

            # Ротация: удаляем старые бэкапы
            self._rotate_backups()

            return str(backup_path)
        except Exception as exc:
            logger.error("Failed to create backup: %s", exc)
            return None

    def _rotate_backups(self) -> None:
        """Удаляет старые бэкапы, оставляя только N последних."""
        try:
            backups = sorted(
                [f for f in self.backup_dir.iterdir() if f.name.startswith("backup_")],
                key=lambda p: p.stat().st_mtime,
                reverse=True,  # Новые первыми
            )
            for old_backup in backups[self.keep_count:]:
                try:
                    old_backup.unlink()
                    logger.debug("Removed old backup: %s", old_backup.name)
                except OSError as exc:
                    logger.warning("Failed to remove old backup %s: %s", old_backup.name, exc)
        except Exception as exc:
            logger.error("Failed to rotate backups: %s", exc)

    def get_backup_list(self) -> list[str]:
        """Возвращает список всех имеющихся бэкапов (имена файлов), новые первыми."""
        try:
            backups = sorted(
                [f.name for f in self.backup_dir.iterdir() if f.name.startswith("backup_")],
                reverse=True,
            )
            return backups
        except Exception:
            return []
