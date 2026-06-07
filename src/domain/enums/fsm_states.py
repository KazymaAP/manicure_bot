"""
src/domain/enums/fsm_states.py — FSM состояния.

FIXED BUG-5: разделены конфликтующие состояния AdminFSM.waiting_for_date на три отдельных:
- waiting_for_slot_date   — добавление временного слота
- waiting_for_toggle_date — открытие/закрытие дня
- waiting_for_template_date — применение шаблона расписания

ADDED: отдельные FSM-состояния для редактирования настроек через бот:
- waiting_for_edit_hours      — редактирование рабочих часов
- waiting_for_edit_interval   — редактирование интервала
- waiting_for_edit_reminder   — редактирование времени напоминания
- waiting_for_service_name    — ввод имени услуги
- waiting_for_service_price   — ввод цены услуги
- waiting_for_service_duration — ввод длительности услуги
- waiting_for_service_select  — выбор услуги для редактирования/удаления
- waiting_for_message_client  — ввод сообщения для клиента
- waiting_for_message_user_id — ввод Telegram ID клиента
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

    FIXED BUG-5: расщеплён waiting_for_date на 3 отдельных состояния:
    - waiting_for_slot_date — добавление слота
    - waiting_for_toggle_date — открытие/закрытие дня
    - waiting_for_template_date — применение шаблона
    Старое waiting_for_date оставлено для обратной совместимости с external хендлерами.
    """
    # main_menu = State()  # REMOVED BUG-10: состояние никогда не использовалось
    waiting_for_appointment_id = State()
    confirming_cancel = State()

    # FIXED BUG-5: разделение конфликтующих состояний
    waiting_for_slot_date = State()      # добавление временного слота
    waiting_for_toggle_date = State()    # открытие/закрытие дня
    waiting_for_template_date = State()  # применение шаблона расписания

    # Оставлено для обратной совместимости (используется в нескольких местах),
    # но новые хендлеры должны использовать специфические состояния выше
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
    # FIXED БАГ-КРИТ-01: отдельное состояние для истории посещений,
    # чтобы не конфликтовать с admin_find_client_query из admin_handler.py
    waiting_for_history_query = State()
    confirming_cancel_all = State()
    confirming_cancel_all_date = State()
    # FIXED: добавлено отсутствующее состояние для разблокировки пользователя
    waiting_for_unblock_user_id = State()

    # FIXED BUG-3: новые состояния для редактирования настроек через бот
    waiting_for_edit_hours = State()        # редактирование рабочих часов
    waiting_for_edit_interval = State()     # редактирование интервала
    waiting_for_edit_reminder = State()     # редактирование времени напоминания
    waiting_for_service_name = State()      # ввод имени новой/редактируемой услуги
    waiting_for_service_price = State()     # ввод цены услуги
    waiting_for_service_duration = State()  # ввод длительности услуги
    waiting_for_service_select = State()    # выбор услуги для редактирования/удаления
    waiting_for_message_client = State()    # ввод текста сообщения клиенту
    waiting_for_message_user_id = State()   # ввод Telegram ID клиента
