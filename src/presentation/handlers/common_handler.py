# src/presentation/handlers/common_handler.py
"""Общие обработчики: /start, /help, проверка подписки."""

import logging
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery

from src.config.dependencies import Container
from src.presentation.keyboards.main_menu import MainMenuKeyboard
from src.presentation.formatters.message_formatter import MessageFormatter

logger = logging.getLogger(__name__)


def _get_portfolio(settings) -> str | None:
    """Возвращает URL портфолио или None если не задан."""
    return settings.portfolio_url or None


router = Router(name="common")


def setup_common_router(container: Container) -> Router:
    """Фабрика роутера — привязывает контейнер к хэндлерам."""

    settings = container.settings

    async def _check_subscription(user_id: int, bot) -> bool:
        """Проверяет подписку пользователя на канал (если задан).

        Теперь:
        - администраторы (из настроек) обходят проверку подписки;
        - при ошибке проверки (исключение от Telegram API) проверка НЕ блокирует пользователя
          — возвращается True, чтобы исключить ложные блокировки, когда бот не может связаться с API.
        """
        if not settings.required_channel:
            return True

        # Админы всегда могут пользоваться ботом
        try:
            if user_id in settings.admin_ids:
                return True
        except Exception:
            # В редком случае, если settings.admin_ids некорректны — продолжаем обычную проверку
            pass

        try:
            member = await bot.get_chat_member(settings.required_channel, user_id)
            status = getattr(member, "status", None)
            # Явные статусы, при которых пользование запрещено
            if status in ("left", "kicked", "banned"):
                return False
            # Если у объекта есть флаг is_member — используем его (новые версии aiogram)
            is_member_flag = getattr(member, "is_member", None)
            if is_member_flag is not None:
                return bool(is_member_flag)
            # По умолчанию считаем, что пользователь подписан
            return True
        except Exception as exc:
            # Расширенное логирование для отладки: попробуем получить информацию о чате и залогировать исключение
            try:
                chat = await bot.get_chat(settings.required_channel)
                logger.debug(
                    "Chat info: chat=%s id=%s title=%s type=%s",
                    settings.required_channel,
                    getattr(chat, "id", None),
                    getattr(chat, "title", None),
                    getattr(chat, "type", None),
                )
            except Exception as chat_exc:
                logger.debug("Не удалось получить chat info: %s", chat_exc)

            try:
                from aiogram.exceptions import TelegramBadRequest
            except Exception:
                TelegramBadRequest = None

            msg = str(exc).lower()
            # Полный трейс ошибки — полезно для дебага
            logger.exception("Ошибка при вызове get_chat_member: %s", msg)

            if TelegramBadRequest is not None and isinstance(exc, TelegramBadRequest):
                logger.info(
                    "TelegramBadRequest при проверке подписки для пользователя %s: %s",
                    user_id, msg
                )
                # Тексты, которые однозначно означают отсутствие подписки
                missing_indicators = (
                    "user not found",
                    "member not found",
                    "not a member",
                    "user not participant",
                    "user is not a participant",
                    "participant",
                )

                # Если видим, что участник не найден — попробуем ещё раз, получив сначала chat.id
                if any(substr in msg for substr in missing_indicators):
                    logger.debug("Попытка повторной проверки через get_chat -> get_chat_member для %s", settings.required_channel)
                    try:
                        chat = await bot.get_chat(settings.required_channel)
                        chat_id = getattr(chat, "id", None)
                        logger.debug("Получен chat.id=%s title=%s", chat_id, getattr(chat, "title", None))
                        if chat_id is not None:
                            try:
                                member2 = await bot.get_chat_member(chat_id, user_id)
                                status2 = getattr(member2, "status", None)
                                logger.debug("Повторная проверка статуса участника: %s", status2)
                                if status2 in ("left", "kicked", "banned"):
                                    return False
                                is_member_flag2 = getattr(member2, "is_member", None)
                                if is_member_flag2 is not None:
                                    return bool(is_member_flag2)
                                return True
                            except Exception as exc2:
                                logger.debug("Повторная проверка get_chat_member не удалась: %s", exc2)
                                # Не блокируем при повторной ошибке — считаем временной проблемой
                                logger.warning(
                                    "Повторная проверка подписки не удалась для пользователя %s в канале %s: %s. Не блокируем доступ.",
                                    user_id, settings.required_channel, exc2
                                )
                                return True
                    except Exception as chat_exc:
                        logger.debug("Не удалось получить chat при повторной проверке: %s", chat_exc)
                        # Если не можем получить chat — считаем временной ошибкой и не блокируем
                        return True

                # Явное указание на недоступность списка участников — логируем подсказку и считаем временной проблемой
                if "member list is inaccessible" in msg or "have no rights" in msg or "have no rights to do that" in msg:
                    logger.warning(
                        "Проверка подписки вернула TelegramBadRequest (%s). Проверьте, что бот является администратором канала %s и имеет доступ к списку участников.",
                        msg, settings.required_channel
                    )
                    # Не блокируем в этом случае, т.к. бот не может проверить
                    return True

                # Другие тексты ошибок трактуем как отсутствие подписки
                logger.warning(
                    "Проверка подписки вернула TelegramBadRequest (%s). Требуется проверка подписки для пользователя %s на канале %s.",
                    msg, user_id, settings.required_channel
                )
                return False

            logger.warning(
                "Ошибка проверки подписки для пользователя %s на канал %s: %s",
                user_id, settings.required_channel, exc
            )
            # Не блокировать пользователя при прочих временных ошибках связи с API
            return True

    @router.message(CommandStart())
    async def cmd_start(message: Message) -> None:
        user_id = message.from_user.id
        is_subscribed = await _check_subscription(user_id, message.bot)

        if not is_subscribed:
            await message.answer(
                MessageFormatter.error_subscription_required(settings.required_channel),
                parse_mode="HTML",
            )
            return

        is_admin = user_id in settings.admin_ids
        portfolio = _get_portfolio(settings)
        await message.answer(
            MessageFormatter.welcome(message.from_user.username),
            reply_markup=MainMenuKeyboard.main(
                is_admin=is_admin,
                portfolio_url=portfolio,
            ),
            parse_mode="HTML",
        )

    @router.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        await message.answer(
            MessageFormatter.help_text(),
            parse_mode="HTML",
        )

    @router.message(F.text == "🏠 Главное меню")
    async def main_menu_button(message: Message) -> None:
        is_admin = message.from_user.id in settings.admin_ids
        portfolio = _get_portfolio(settings)
        await message.answer(
            MessageFormatter.main_menu_title(),
            reply_markup=MainMenuKeyboard.main(is_admin=is_admin, portfolio_url=portfolio),
        )

    return router
