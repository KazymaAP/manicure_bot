"""
src/domain/exceptions/base.py — Базовый класс доменных исключений.
"""
from __future__ import annotations


class DomainError(Exception):
    """Базовое исключение для бизнес-логики приложения.

    Все доменные исключения наследуются от этого класса,
    что позволяет поймать любую доменную ошибку одним except.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.message!r})"


class ValidationError(DomainError):
    """Ошибка валидации входных данных."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"Validation error for '{field}': {message}")
        self.field = field
