"""
src/config/logging_config.py — Настройка логирования.

Улучшения v4.1:
- RotatingFileHandler вместо FileHandler (предотвращает бесконечный рост лог-файла)
- Явная настройка root logger вместо basicConfig
- Подавление шумных сторонних библиотек
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

# 10 МБ на файл, 5 ротаций = максимум ~50 МБ логов
_MAX_BYTES = 10 * 1024 * 1024
_BACKUP_COUNT = 5


def setup_logging(log_level: str = "INFO", log_file: str | None = None) -> None:
    """Настраивает логирование приложения.

    Использует явную настройку root logger вместо basicConfig,
    чтобы избежать повторной настройки (basicConfig игнорируется при повторном вызове).

    Файловые логи автоматически ротируются при достижении 10 МБ (хранится 5 файлов).
    Это предотвращает бесконечный рост лог-файла при долгой работе бота.

    Args:
        log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Путь к файлу логов. None — только stdout.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    # Очищаем существующие хэндлеры, чтобы избежать дублирования при повторном вызове
    root_logger.handlers.clear()
    root_logger.setLevel(level)

    # Консольный вывод
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(fmt)
    root_logger.addHandler(stdout_handler)

    # Файловый вывод с ротацией
    if log_file:
        try:
            file_handler = RotatingFileHandler(
                log_file,
                encoding="utf-8",
                maxBytes=_MAX_BYTES,
                backupCount=_BACKUP_COUNT,
            )
            file_handler.setFormatter(fmt)
            root_logger.addHandler(file_handler)
        except (OSError, IOError) as e:
            root_logger.warning("Failed to open log file %r: %s", log_file, e)

    # Подавляем лишние логи сторонних библиотек на уровне WARNING
    for noisy_lib in ("aiogram", "aiohttp", "apscheduler"):
        logging.getLogger(noisy_lib).setLevel(logging.WARNING)
