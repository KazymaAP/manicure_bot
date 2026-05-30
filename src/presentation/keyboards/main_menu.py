"""
src/presentation/keyboards/main_menu.py — Клавиатуры главного меню.

✅ Из v2_tar: MainMenuKeyboard class с static methods
"""
from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import ReplyKeyboardBuilder


class MainMenuKeyboard:
    """Клавиатуры главного меню пользователя."""

    @staticmethod
    def main(is_admin: bool = False, portfolio_url: str | None = None) -> ReplyKeyboardMarkup:
        """Главное меню пользователя.

        Args:
            is_admin: Если True, добавляет админ кнопку.
            portfolio_url: Ссылка на портфолио (если задана — добавляет кнопку).
        """
        builder = ReplyKeyboardBuilder()
        builder.row(KeyboardButton(text="📅 Записаться"))
        builder.row(KeyboardButton(text="📋 Мои записи"))
        if portfolio_url:
            builder.row(
                KeyboardButton(text="💅 Портфолио", web_app=WebAppInfo(url=portfolio_url))
            )
        if is_admin:
            builder.row(KeyboardButton(text="⚙️ Админ-панель"))
        return builder.as_markup(resize_keyboard=True)

    @staticmethod
    def subscribe(channel_link: str) -> ReplyKeyboardMarkup:
        """Кнопки подписки на канал.

        Args:
            channel_link: Ссылка на канал.
        """
        builder = ReplyKeyboardBuilder()
        builder.row(KeyboardButton(text="📢 Подписаться"))
        return builder.as_markup(resize_keyboard=True)

    @staticmethod
    def back_to_main() -> ReplyKeyboardMarkup:
        """Кнопка возврата в главное меню."""
        builder = ReplyKeyboardBuilder()
        builder.row(KeyboardButton(text="🏠 Главное меню"))
        return builder.as_markup(resize_keyboard=True)
