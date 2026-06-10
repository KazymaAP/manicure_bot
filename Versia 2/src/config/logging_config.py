"""
src/config/logging_config.py — Настройка структурированного логирования.

Особенности:
- RotatingFileHandler (10 МБ × 5 файлов = макс. 50 МБ)
- Явная настройка root logger (безопасный повторный вызов)
- Подавление шумных сторонних библиотек на WARNING
- Структурированный формат с именем модуля
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

# 10 МБ на файл, 5 ротаций = максимум ~50 МБ логов
_MAX_BYTES = 10 * 1024 * 1024
_BACKUP_COUNT = 5

# Уровни по умолчанию для сторонних библиотек
_NOISY_LIBS: dict[str, int] = {
    "aiogram": logging.WARNING,
    "aiohttp": logging.WARNING,
    "apscheduler": logging.WARNING,
    "urllib3": logging.WARNING,
    "asyncio": logging.WARNING,
}


def setup_logging(log_level: str = "INFO", log_file: str | None = None) -> None:
    """Настраивает логирование приложения.

    Использует явную настройку root logger вместо basicConfig.
    Файловые логи автоматически ротируются при достижении 10 МБ.

    Args:
        log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Путь к файлу логов. None — только stdout.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Расширенный формат: время + уровень + имя модуля + сообщение
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s:%(lineno)d — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Краткий формат для консоли
    console_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    root_logger = logging.getLogger()
    # Очищаем существующие хэндлеры, чтобы избежать дублирования
    root_logger.handlers.clear()
    root_logger.setLevel(level)

    # ── Консольный вывод ──────────────────────────────────────────────────
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(console_fmt)
    stdout_handler.setLevel(level)
    root_logger.addHandler(stdout_handler)

    # ── Файловый вывод с ротацией ─────────────────────────────────────────
    if log_file:
        try:
            file_handler = RotatingFileHandler(
                log_file,
                encoding="utf-8",
                maxBytes=_MAX_BYTES,
                backupCount=_BACKUP_COUNT,
            )
            file_handler.setFormatter(fmt)
            file_handler.setLevel(level)
            root_logger.addHandler(file_handler)
            root_logger.debug("File logging enabled: %s (max %dMB × %d)", log_file, _MAX_BYTES // 1024 // 1024, _BACKUP_COUNT)
        except OSError as exc:
            root_logger.warning("Failed to open log file %r: %s", log_file, exc)

    # ── Тишина от сторонних библиотек ────────────────────────────────────
    for lib_name, lib_level in _NOISY_LIBS.items():
        logging.getLogger(lib_name).setLevel(max(level, lib_level))
