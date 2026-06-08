"""
src/presentation/keyboards/notifications.py — Клавиатура управления уведомлениями.

ПРОБЛЕМА 2/16 FIX: клавиатура вынесена из final_features_handler.py в отдельный файл
в соответствии с принципом разделения ответственности. Это позволяет переиспользовать
клавиатуру из любых хендлеров без дублирования кода.
"""
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class NotificationKeyboard:
    """Клавиатуры для управления настройками уведомлений пользователя."""

    @staticmethod
    def settings(notif_settings: dict) -> InlineKeyboardMarkup:
        """Строит клавиатуру настроек уведомлений.

        Args:
            notif_settings: Словарь с ключами notifications_enabled, notif_24h,
                            notif_2h, notif_1h (целые числа 0 или 1).

        Returns:
            InlineKeyboardMarkup с кнопками переключения уведомлений.
        """
        all_on = notif_settings.get("notifications_enabled", 1)
        h24 = notif_settings.get("notif_24h", 1)
        h2 = notif_settings.get("notif_2h", 1)
        h1 = notif_settings.get("notif_1h", 1)
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"{'✅' if all_on else '❌'} Все уведомления",
                callback_data="notif_all_on" if not all_on else "notif_all_off"
            )],
            [InlineKeyboardButton(
                text=f"{'🔔' if h24 else '🔕'} За 24 часа",
                callback_data="notif_24h"
            )],
            [InlineKeyboardButton(
                text=f"{'🔔' if h2 else '🔕'} За 2 часа",
                callback_data="notif_2h"
            )],
            [InlineKeyboardButton(
                text=f"{'🔔' if h1 else '🔕'} За 1 час",
                callback_data="notif_1h"
            )],
        ])
