"""
src/presentation/keyboards/main_menu.py — Клавиатуры главного меню.

Обновлено: 4 кнопки для клиента — «Записаться», «Мои записи», «Цены», «Связаться с мастером».
Тёплый, простой интерфейс без лишних элементов.
"""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


class MainMenuKeyboard:
    """Клавиатуры главного меню пользователя."""

    @staticmethod
    def main(is_admin: bool = False, portfolio_url: str | None = None) -> ReplyKeyboardMarkup:
        """
        Главное меню клиента.
        Основные 4 кнопки: Записаться, Мои записи, Цены, Связаться с мастером.
        """
        builder = ReplyKeyboardBuilder()
        # Первая строка — самые важные действия
        builder.row(
            KeyboardButton(text="💅 Записаться"),
            KeyboardButton(text="📋 Мои записи")
        )
        # Вторая строка — информация
        builder.row(
            KeyboardButton(text="💰 Цены"),
            KeyboardButton(text="📞 Связаться с мастером")
        )
        # Портфолио (если задано)
        if portfolio_url:
            builder.row(
                KeyboardButton(text="🖼 Портфолио", web_app=WebAppInfo(url=portfolio_url))
            )
        # Кнопка администратора — только для мастера
        if is_admin:
            builder.row(KeyboardButton(text="⚙️ Админ-панель"))
        return builder.as_markup(resize_keyboard=True)

    @staticmethod
    def subscribe(channel_link: str) -> InlineKeyboardMarkup:
        """Кнопка подписки на канал с последующей проверкой."""
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться", url=channel_link)],
            [InlineKeyboardButton(text="✅ Я подписалась", callback_data="check_subscription")],
        ])
        return kb

    @staticmethod
    def back_to_main() -> ReplyKeyboardMarkup:
        """Кнопка возврата в главное меню."""
        builder = ReplyKeyboardBuilder()
        builder.row(KeyboardButton(text="🏠 Главное меню"))
        return builder.as_markup(resize_keyboard=True)

    @staticmethod
    def book_again() -> InlineKeyboardMarkup:
        """Кнопка 'Записаться снова' после визита."""
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="💅 Записаться снова", callback_data="book_again"))
        return builder.as_markup()
