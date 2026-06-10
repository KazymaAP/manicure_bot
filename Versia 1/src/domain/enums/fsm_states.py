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
    # BUG 1.5 FIX: transferring_confirming удалено — мёртвый код, никогда не устанавливалось.
    # Подтверждение переноса реализовано inline в transfer_confirm_new_slot.


class AdminFSM(StatesGroup):
    """Состояния FSM для панели администратора.

    FIXED BUG-10: удалено состояние main_menu — никогда не устанавливалось через
    state.set_state(AdminFSM.main_menu), хендлеры с этим фильтром никогда не срабатывали.
    Удаление исключает путаницу в коде. Вход в /admin не требует FSM-состояния.

    FIXED BUG-5: расщеплён waiting_for_date на 3 отдельных состояния:
    - waiting_for_slot_date — добавление слота
    - waiting_for_toggle_date — открытие/закрытие дня
    - waiting_for_template_date — применение шаблона
    БАГ 15 FIX: waiting_for_date УДАЛЕНО — дублирующий мёртвый код устранён.
    """
    # main_menu = State()  # REMOVED BUG-10: состояние никогда не использовалось
    waiting_for_appointment_id = State()
    confirming_cancel = State()

    # FIXED BUG-5: разделение конфликтующих состояний
    waiting_for_slot_date = State()      # добавление временного слота
    waiting_for_toggle_date = State()    # открытие/закрытие дня
    waiting_for_template_date = State()  # применение шаблона расписания

    # БАГ 15 FIX: waiting_for_date УДАЛЕНО — мёртвый код.
    # Хендлер admin_add_slot_date перенесён на waiting_for_slot_date.
    # Все новые хендлеры должны использовать специфические состояния выше.
    waiting_for_time = State()

    # FIXED: дополнительные состояния для админ-фич
    # ПРОБЛЕМА 4 FIX: waiting_for_broadcast удалено — мёртвый код, нигде не вызывалось через
    # state.set_state(AdminFSM.waiting_for_broadcast). Вместо него используются:
    # waiting_for_broadcast_text (рассылка), waiting_for_welcome_text, waiting_for_photo_url.
    # BUG 3.1 FIX: waiting_for_export_range удалено — мёртвый код (никогда не устанавливалось)
    waiting_for_template_name = State()
    waiting_for_template_schedule = State()
    waiting_for_blacklist_id = State()
    # BUG 3.1 FIX: waiting_for_block_reason удалено — мёртвый код
    waiting_for_search_query = State()
    # FIXED БАГ-КРИТ-01: отдельное состояние для истории посещений,
    # чтобы не конфликтовать с admin_find_client_query из admin_handler.py
    waiting_for_history_query = State()
    # BUG 3.1 FIX: confirming_cancel_all удалено — использовался confirming_cancel_all_date
    confirming_cancel_all_date = State()
    # BUG 3.1 FIX: waiting_for_unblock_user_id удалено — мёртвый код (используется waiting_for_blacklist_id)

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

    # FIXED БАГ #14: отдельные состояния вместо переиспользования waiting_for_broadcast
    waiting_for_welcome_text = State()      # редактирование текста приветствия
    waiting_for_photo_url = State()         # редактирование URL фото приветствия
    waiting_for_broadcast_text = State()    # рассылка сообщений
