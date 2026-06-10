"""
src/presentation/handlers/__init__.py

ПРОБЛЕМА 19 FIX: экспорт setup-функций роутеров.
Позволяет импортировать setup-функции из одного места вместо отдельных from-import.
"""
from src.presentation.handlers.admin_handler import setup_admin_router
from src.presentation.handlers.common_handler import setup_common_router
from src.presentation.handlers.extended_features_handler import setup_extended_features_router
from src.presentation.handlers.final_features_handler import setup_final_features_router
from src.presentation.handlers.user_handler import setup_user_router

__all__ = [
    "setup_admin_router",
    "setup_common_router",
    "setup_extended_features_router",
    "setup_final_features_router",
    "setup_user_router",
]
