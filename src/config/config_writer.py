"""
src/config/config_writer.py — Вспомогательный модуль для записи config.json.

BUG 2.2 FIX: _save_config вынесена из вложенных функций admin_handler.py
в отдельный модуль для переиспользования.

Используется в:
- src/presentation/handlers/admin_handler.py (атомарное сохранение настроек)
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import tempfile

logger = logging.getLogger(__name__)

_config_write_lock = asyncio.Lock()


async def save_config(config: dict, config_path: str | None = None) -> None:
    """Атомарно сохраняет config.json через временный файл + os.replace().

    FIXED HIGH-03: asyncio.Lock для защиты от concurrent записей (race condition).
    Временный файл + os.replace() гарантируют атомарность (нет partial write).

    Args:
        config: Словарь конфигурации для сохранения.
        config_path: Путь к config.json. По умолчанию — относительно этого модуля.
    """
    if config_path is None:
        config_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "config.json")
        )

    async with _config_write_lock:
        config_dir = os.path.dirname(config_path)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8",
                dir=config_dir, suffix=".tmp", delete=False,
            ) as tmp_f:
                tmp_path = tmp_f.name
                json.dump(config, tmp_f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, config_path)
            tmp_path = None
            # Инвалидируем кэш _load_config_json
            try:
                from src.config.dependencies import _load_config_json
                _load_config_json.cache_clear()
                logger.debug("config.json cache invalidated after save")
            except Exception as exc:
                logger.debug("Suppressed: cache_clear error: %s", exc, exc_info=True)
            logger.debug("config.json saved atomically to %s", config_path)
        except Exception as exc:
            logger.error("Failed to save config.json to %s: %s", config_path, exc)
            raise
        finally:
            if tmp_path and os.path.exists(tmp_path):
                with contextlib.suppress(Exception):
                    os.unlink(tmp_path)
