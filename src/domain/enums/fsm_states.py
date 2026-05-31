"""
src/domain/enums/fsm_states.py — FSM состояния.
"""
from aiogram.fsm.state import State, StatesGroup


class BookingFSM(StatesGroup):
    """Состояния FSM для процесса записи клиента."""
    choosing_service = State()
    choosing_date = State()
    choosing_time = State()
    entering_name = State()
    entering_phone = State()
    entering_comment = State()
    confirming = State()
    # FIXED: добавлены состояния для переноса и waitlist
    transferring_choosing_date = State()
    transferring_choosing_time = State()
    transferring_confirming = State()


class AdminFSM(StatesGroup):
    """Состояния FSM для панели администратора.

    FIXED BUG-10: удалено состояние main_menu — никогда не устанавливалось через
    state.set_state(AdminFSM.main_menu), хендлеры с этим фильтром никогда не срабатывали.
    Удаление исключает путаницу в коде. Вход в /admin не требует FSM-состояния.
    """
    # main_menu = State()  # REMOVED BUG-10: состояние никогда не использовалось
    waiting_for_appointment_id = State()
    confirming_cancel = State()
    waiting_for_date = State()
    waiting_for_time = State()
    # FIXED: дополнительные состояния для админ-фич
    waiting_for_broadcast = State()
    waiting_for_export_range = State()
    waiting_for_template_name = State()
    waiting_for_template_schedule = State()
    waiting_for_blacklist_id = State()
    waiting_for_block_reason = State()
    waiting_for_search_query = State()
    confirming_cancel_all = State()
    confirming_cancel_all_date = State()
    # FIXED: добавлено отсутствующее состояние для разблокировки пользователя
    waiting_for_unblock_user_id = State()
