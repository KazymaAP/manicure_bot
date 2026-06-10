-- migrations/005_add_bot_blocked_column.sql
-- FIXED BUG-4: добавляет колонку is_bot_blocked в таблицу users.
-- При Forbidden-ошибке (пользователь заблокировал бота) флаг устанавливается в 1.
-- При отправке уведомлений проверяется этот флаг — пользователи с is_bot_blocked=1
-- исключаются из рассылок без необходимости дополнительных запросов к Telegram API.
-- Это гарантирует что после перезапуска бота заблокировавшие пользователи
-- не получают сообщения снова (в отличие от хранения только в памяти).

ALTER TABLE users ADD COLUMN is_bot_blocked INTEGER NOT NULL DEFAULT 0;

-- Создаём индекс для быстрой фильтрации активных пользователей при рассылке
CREATE INDEX IF NOT EXISTS idx_users_not_blocked ON users (user_id) WHERE is_bot_blocked = 0;
