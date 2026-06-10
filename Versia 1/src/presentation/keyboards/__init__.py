"""
src/presentation/keyboards/__init__.py

ПРОБЛЕМА 17 FIX: добавлен экспорт NotificationKeyboard.
"""
from src.presentation.keyboards.admin import AdminKeyboard
from src.presentation.keyboards.booking import BookingKeyboard
from src.presentation.keyboards.calendar import CalendarKeyboard
from src.presentation.keyboards.main_menu import MainMenuKeyboard
from src.presentation.keyboards.notifications import NotificationKeyboard

__all__ = [
    "AdminKeyboard",
    "BookingKeyboard",
    "CalendarKeyboard",
    "MainMenuKeyboard",
    "NotificationKeyboard",
]
