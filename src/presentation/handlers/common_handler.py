"""
src/presentation/handlers/common_handler.py — Общие обработчики.

Обновлено: тёплое приветствие с именем мастера, цены-карточки,
контактная информация, кнопка «Связаться с мастером».

BUG 2.1 FIX: _check_subscription вынесена на уровень модуля с параметром settings,
чтобы её можно было импортировать и использовать в user_handler.py.
"""

import contextlib
import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.config.dependencies import Container
from src.presentation.formatters.message_formatter import MessageFormatter
from src.presentation.keyboards.main_menu import MainMenuKeyboard

logger = logging.getLogger(__name__)


def _get_portfolio(settings) -> str | None:
    """Возвращает URL портфолио или None если не задан."""
    return settings.portfolio_url


async def check_subscription(user_id: int, bot, settings) -> bool:
    """
    BUG 2.1 FIX: Проверяет подписку пользователя на канал.
    Вынесена на уровень модуля для переиспользования в user_handler.py.
    Ранее эта логика дублировалась inline в start_booking и my_appointments.
    """
    if not settings.required_channel:
        return True
    try:
        if user_id in settings.admin_ids:
            return True
    except Exception:
        pass
    try:
        member = await bot.get_chat_member(settings.required_channel, user_id)
        status = getattr(member, "status", None)
        if status in ("left", "kicked", "banned"):
            return False
        is_member_flag = getattr(member, "is_member", None)
        if is_member_flag is not None:
            return bool(is_member_flag)
        return True
    except Exception as exc:
        logger.warning("Ошибка проверки подписки для %s: %s", user_id, exc)
        return True


router = Router(name="common")


def setup_common_router(container: Container) -> Router:
    """Фабрика роутера — привязывает контейнер к хэндлерам."""

    settings = container.settings

    async def _check_subscription(user_id: int, bot) -> bool:
        """Внутренняя обёртка над check_subscription с захваченным settings."""
        return await check_subscription(user_id, bot, settings)

    # ── /start — приветственное сообщение ────────────────────────────────
    @router.message(CommandStart())
    async def cmd_start(message: Message) -> None:
        """Тёплое приветствие с именем клиента и красивым главным меню."""
        import asyncio

        user_id = message.from_user.id
        is_subscribed = await _check_subscription(user_id, message.bot)

        if not is_subscribed:
            await message.answer(
                MessageFormatter.error_subscription_required(settings.required_channel),
                reply_markup=MainMenuKeyboard.subscribe(settings.required_channel),
                parse_mode="HTML",
            )
            return

        is_admin = user_id in settings.admin_ids
        portfolio = _get_portfolio(settings)

        # Пытаемся получить имя из предыдущей записи (персонализация)
        appt_service = container.appointment_service
        greeting_name = None
        try:
            last_appt = await asyncio.to_thread(appt_service.get_last_appointment, user_id)
            if last_appt and last_appt.client_name:
                greeting_name = last_appt.client_name
        except Exception:
            pass

        # Используем имя из Telegram если нет из записи
        display_name = greeting_name or message.from_user.first_name or message.from_user.username or "дорогой гость"

        welcome_text = MessageFormatter.welcome_banner(display_name)

        # Отправляем фото приветствия, если оно задано в настройках
        if getattr(settings, 'welcome_photo_url', None):
            try:
                await message.answer_photo(
                    photo=settings.welcome_photo_url,
                    caption=welcome_text,
                    reply_markup=MainMenuKeyboard.main(is_admin=is_admin, portfolio_url=portfolio),
                    parse_mode="HTML",
                )
                return
            except Exception as e:
                logger.warning("Не удалось отправить фото приветствия: %s", e)

        await message.answer(
            welcome_text,
            reply_markup=MainMenuKeyboard.main(is_admin=is_admin, portfolio_url=portfolio),
            parse_mode="HTML",
        )

    # ── Проверка подписки ─────────────────────────────────────────────────
    @router.callback_query(F.data == "check_subscription")
    async def check_subscription_cb(callback: CallbackQuery) -> None:
        """Обработчик кнопки 'Я подписалась' — перепроверяет подписку."""
        user_id = callback.from_user.id
        is_subscribed = await _check_subscription(user_id, callback.bot)
        if is_subscribed:
            is_admin = user_id in settings.admin_ids
            portfolio = _get_portfolio(settings)
            display_name = callback.from_user.first_name or callback.from_user.username or "дорогой гость"
            await callback.message.edit_text(
                MessageFormatter.welcome_banner(display_name),
                reply_markup=MainMenuKeyboard.main(is_admin=is_admin, portfolio_url=portfolio),
                parse_mode="HTML",
            )
            await callback.answer("Проверка пройдена — добро пожаловать! 🌸")
        else:
            await callback.answer(
                "Вы ещё не подписались. Нажмите '📢 Подписаться' и затем '✅ Я подписалась'",
                show_alert=True
            )

    # ── /help ──────────────────────────────────────────────────────────────
    @router.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        await message.answer(
            MessageFormatter.help_text(),
            parse_mode="HTML",
        )

    # ── /cancel — сброс FSM ────────────────────────────────────────────────
    @router.message(Command("cancel"))
    async def cmd_cancel(message: Message, state: FSMContext) -> None:
        """Сброс текущего FSM-состояния."""
        current_state = await state.get_state()
        if current_state is None:
            await message.answer("Нет активного действия для отмены.")
            return
        await state.clear()
        is_admin = message.from_user.id in settings.admin_ids
        portfolio = _get_portfolio(settings)
        await message.answer(
            "Действие отменено. Возвращаемся в главное меню 🌸",
            reply_markup=MainMenuKeyboard.main(is_admin=is_admin, portfolio_url=portfolio),
        )

    # ── Главное меню (кнопка) ─────────────────────────────────────────────
    @router.message(F.text == "🏠 Главное меню")
    async def main_menu_button(message: Message, state: FSMContext) -> None:
        await state.clear()
        is_admin = message.from_user.id in settings.admin_ids
        portfolio = _get_portfolio(settings)
        await message.answer(
            MessageFormatter.main_menu_title(),
            reply_markup=MainMenuKeyboard.main(is_admin=is_admin, portfolio_url=portfolio),
        )

    # ── Цены ──────────────────────────────────────────────────────────────
    @router.message(F.text.in_({"💰 Цены", "💰 Прайс"}))
    async def prices_handler(message: Message) -> None:
        """Показывает прайс-лист на услуги."""
        services = settings.services or {}
        text = MessageFormatter.prices_list(services)
        await message.answer(text, parse_mode="HTML")

    # ── Связаться с мастером ──────────────────────────────────────────────
    @router.message(F.text.in_({"📞 Связаться с мастером", "📞 Контакты"}))
    async def contacts_handler(message: Message) -> None:
        """Показывает контактную информацию мастера."""
        # Получаем username первого admin_id как контакт мастера
        master_username = None
        if settings.admin_ids:
            try:
                chat = await message.bot.get_chat(settings.admin_ids[0])
                master_username = getattr(chat, 'username', None)
            except Exception:
                pass

        text = MessageFormatter.contacts_text(
            phone=getattr(settings, 'phone', None),
            instagram=getattr(settings, 'instagram', None),
            address=getattr(settings, 'address', None),
            maps_link=getattr(settings, 'maps_link', None),
            master_username=master_username,
        )

        # Кнопка "Написать мастеру" если есть username
        if master_username:
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="✉️ Написать мастеру",
                    url=f"https://t.me/{master_username}"
                )]
            ])
            await message.answer(text, parse_mode="HTML", reply_markup=kb)
        else:
            await message.answer(text, parse_mode="HTML")

    # ── Callback: книга записаться снова ──────────────────────────────────
    @router.callback_query(F.data == "book_again_start")
    async def book_again_start(callback: CallbackQuery, state: FSMContext) -> None:
        """Запускает процесс новой записи из кнопки 'Записаться снова'."""
        await state.clear()
        # Редиректим на начало записи
        from src.domain.enums.fsm_states import BookingFSM
        await state.set_state(BookingFSM.choosing_service)
        await callback.message.answer(
            MessageFormatter.choose_service(),
            reply_markup=__import__(
                'src.presentation.keyboards.booking', fromlist=['BookingKeyboard']
            ).BookingKeyboard.service_selection(settings.services or None),
            parse_mode="HTML",
        )
        await callback.answer()

    # ── Обратная совместимость: старый callback book_again ─────────────────
    @router.callback_query(F.data == "book_again")
    async def book_again_compat(callback: CallbackQuery, state: FSMContext) -> None:
        """FIXED БАГ #19: обратная совместимость со старым callback_data 'book_again'."""
        await book_again_start(callback, state)

    # ── Inline callback: возврат в главное меню ───────────────────────────
    @router.callback_query(F.data == "main_menu")
    async def inline_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
        """Возврат в главное меню из inline-кнопки."""
        await state.clear()
        is_admin = callback.from_user.id in settings.admin_ids
        portfolio = _get_portfolio(settings)
        with contextlib.suppress(Exception):
            await callback.message.edit_text(
                MessageFormatter.main_menu_title(),
                reply_markup=None,
            )
        await callback.message.answer(
            MessageFormatter.main_menu_title(),
            reply_markup=MainMenuKeyboard.main(is_admin=is_admin, portfolio_url=portfolio),
            parse_mode="HTML",
        )
        await callback.answer()

    return router
