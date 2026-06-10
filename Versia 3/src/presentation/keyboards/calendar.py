"""
src/presentation/keyboards/calendar.py — Inline-календарь.

✅ Из v2_tar: CalendarKeyboard class с русскими названиями
✅ Из v1: логика available_dates из get_available_dates_set
"""
from __future__ import annotations

import calendar
from datetime import date

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.presentation.constants import CALENDAR_IGNORE_CB, MONTHS_RU, WEEKDAYS_RU

IGNORE_CB = CALENDAR_IGNORE_CB


class CalendarKeyboard:
    """Построитель inline-календаря для выбора даты."""

    @staticmethod
    def build(
        year: int,
        month: int,
        available_dates: set[str],
        prefix: str = "cal",
    ) -> InlineKeyboardMarkup:
        """Строит inline-календарь на заданный месяц.

        Помечает доступные даты (✅) и прошедшие (✖️).

        Args:
            year: Год.
            month: Месяц (1-12).
            available_dates: Множество дат «YYYY-MM-DD».
            prefix: Префикс callback_data для кнопок навигации.

        Returns:
            Готовая inline-клавиатура.
        """
        builder = InlineKeyboardBuilder()

        # Заголовок: навигация по месяцам
        builder.row(
            InlineKeyboardButton(
                text="◀️",
                callback_data=f"{prefix}_prev:{year}:{month}",
            ),
            InlineKeyboardButton(
                text=f"{MONTHS_RU[month]} {year}",
                callback_data=IGNORE_CB,
            ),
            InlineKeyboardButton(
                text="▶️",
                callback_data=f"{prefix}_next:{year}:{month}",
            ),
        )

        # Дни недели
        builder.row(
            *[InlineKeyboardButton(text=d, callback_data=IGNORE_CB) for d in WEEKDAYS_RU]
        )

        # Дни месяца
        today = date.today()
        for week in calendar.monthcalendar(year, month):
            row_buttons = [
                CalendarKeyboard._day_button(day, year, month, today, available_dates, prefix)
                for day in week
            ]
            builder.row(*row_buttons)

        return builder.as_markup()

    @staticmethod
    def _day_button(
        day: int,
        year: int,
        month: int,
        today: date,
        available_dates: set[str],
        prefix: str,
    ) -> InlineKeyboardButton:
        """Создаёт кнопку для конкретного дня.

        Args:
            day: Число месяца (0 = пустая ячейка).
            year: Год.
            month: Месяц.
            today: Сегодняшняя дата.
            available_dates: Доступные даты.
            prefix: Префикс callback_data.

        Returns:
            Кнопка InlineKeyboardButton.
        """
        if day == 0:
            return InlineKeyboardButton(text=" ", callback_data=IGNORE_CB)

        current = date(year, month, day)
        date_str = current.isoformat()

        if current < today:
            return InlineKeyboardButton(text=f"✖️{day}", callback_data=IGNORE_CB)
        if date_str in available_dates:
            return InlineKeyboardButton(
                text=f"✅{day}",
                callback_data=f"{prefix}_day:{date_str}",
            )
        return InlineKeyboardButton(text=str(day), callback_data=IGNORE_CB)
