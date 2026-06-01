"""
src/application/services/backup_service.py — Сервис автоматического бэкапа БД.

FIXED: Резервные копии SQLite с ротацией (хранить N последних).
"""
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class BackupService:
    """Управляет резервными копиями SQLite базы данных."""

    def __init__(self, db_path: str, backup_dir: str = "data/backups", keep_count: int = 7):
        """Инициализирует сервис бэкапа.

        Args:
            db_path: Путь к файлу БД (например, data/manicure_bot.db).
            backup_dir: Директория для сохранения бэкапов.
            keep_count: Сколько последних бэкапов хранить.
        """
        self.db_path = db_path
        self.backup_dir = backup_dir
        self.keep_count = keep_count
        self._ensure_backup_dir()

    def _ensure_backup_dir(self) -> None:
        """Создаёт директорию для бэкапов, если её нет."""
        try:
            Path(self.backup_dir).mkdir(parents=True, exist_ok=True)
            logger.debug("Backup directory ensured: %s", self.backup_dir)
        except Exception as exc:
            logger.error("Failed to create backup directory %s: %s", self.backup_dir, exc)

    def create_backup(self) -> str | None:
        """Создаёт резервную копию БД с ротацией старых файлов.
        
        FIXED: используется sqlite3.backup API вместо shutil.copy2 для безопасного хот-бэкапа
        с корректным обработкой WAL-режима.

        Returns:
            Путь к созданному бэкапу или None при ошибке.
        """
        if not os.path.exists(self.db_path):
            logger.warning("Database file not found: %s", self.db_path)
            return None

        try:
            import sqlite3
            
            # Формируем имя файла с меткой времени
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            db_name = os.path.basename(self.db_path)
            backup_name = f"backup_{timestamp}_{db_name}"
            backup_path = os.path.join(self.backup_dir, backup_name)

            # Используем встроенный SQLite backup API для безопасного хот-бэкапа
            src_conn = sqlite3.connect(self.db_path)
            dst_conn = sqlite3.connect(backup_path)
            
            try:
                # Это корректно обрабатывает WAL и гарантирует консистентность
                src_conn.backup(dst_conn)
                logger.info("Backup created: %s", backup_path)
            finally:
                dst_conn.close()
                src_conn.close()

            # Ротация: удаляем старые бэкапы
            self._rotate_backups()

            return backup_path
        except Exception as exc:
            logger.error("Failed to create backup: %s", exc)
            return None

    def _rotate_backups(self) -> None:
        """Удаляет старые бэкапы, оставляя только N последних."""
        try:
            # Ищем все бэкап-файлы
            backups = sorted(
                [f for f in os.listdir(self.backup_dir) if f.startswith("backup_")],
                reverse=True,  # Новые первыми
            )
            # Удаляем лишние
            for old_backup in backups[self.keep_count :]:
                old_path = os.path.join(self.backup_dir, old_backup)
                try:
                    os.remove(old_path)
                    logger.debug("Removed old backup: %s", old_backup)
                except Exception as exc:
                    logger.warning("Failed to remove old backup %s: %s", old_backup, exc)
        except Exception as exc:
            logger.error("Failed to rotate backups: %s", exc)

    def get_backup_list(self) -> list[str]:
        """Возвращает список всех имеющихся бэкапов (имена файлов)."""
        try:
            return sorted(
                [f for f in os.listdir(self.backup_dir) if f.startswith("backup_")],
                reverse=True,
            )
        except Exception:
            return []
