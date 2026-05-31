"""
src/config/logging_config.py — Настройка логирования.
"""
from __future__ import annotations

import logging
import sys


def setup_logging(log_level: str = "INFO", log_file: str | None = None) -> None:
    """Настраивает логирование приложения.

    FIXED: используем явную настройку root logger вместо basicConfig,
    чтобы избежать повторной настройки (basicConfig игнорируется при повторном вызове,
    что приводило к непредсказуемому поведению).

    Args:
        log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Путь к файлу логов. None — только stdout.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    root_logger = logging.getLogger()
    # Очищаем существующие хэндлеры, чтобы избежать дублирования
    root_logger.handlers.clear()
    root_logger.setLevel(level)

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(fmt)
    root_logger.addHandler(stdout_handler)

    if log_file:
        try:
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(fmt)
            root_logger.addHandler(file_handler)
        except (OSError, IOError) as e:
            root_logger.warning("Failed to open log file %r: %s", log_file, e)

    # Подавляем лишние логи сторонних библиотек
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
