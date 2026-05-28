"""
src/domain/enums/fsm_states.py — FSM состояния.
"""
from aiogram.fsm.state import State, StatesGroup


class BookingFSM(StatesGroup):
    """Состояния FSM для процесса записи клиента."""
    choosing_date = State()
    choosing_time = State()
    entering_name = State()
    entering_phone = State()
    entering_comment = State()
    confirming = State()


class AdminFSM(StatesGroup):
    """Состояния FSM для панели администратора."""
    main_menu = State()
    waiting_for_appointment_id = State()
    confirming_cancel = State()
    waiting_for_date = State()
    waiting_for_time = State()
