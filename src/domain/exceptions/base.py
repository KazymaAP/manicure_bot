"""
src/domain/exceptions/base.py — Базовые исключения домена.
"""


class DomainError(Exception):
    """Базовое исключение домена."""


class ValidationError(DomainError):
    """Ошибка валидации данных."""
