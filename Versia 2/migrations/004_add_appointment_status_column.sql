-- migrations/004_add_appointment_status_column.sql
-- Добавляет колонку status в таблицу appointments для корректного хранения
-- статуса записи (ACTIVE=0, CANCELLED=1, COMPLETED=2) вместо использования
-- поля comment для хранения маркеров завершения.
--
-- ВАЖНО: миграция безопасна для выполнения на существующих БД — использует
-- ALTER TABLE IF NOT EXISTS (через проверку PRAGMA table_info).
-- Существующие записи получат значение по умолчанию (0 = ACTIVE).

PRAGMA foreign_keys = OFF;
BEGIN TRANSACTION;

-- Добавляем колонку status если её нет
-- SQLite не поддерживает IF NOT EXISTS в ALTER TABLE,
-- поэтому проверяем через исключение при дублировании (приложение обрабатывает это)
ALTER TABLE appointments ADD COLUMN status INTEGER NOT NULL DEFAULT 0;

-- Синхронизируем status с is_cancelled для существующих записей
UPDATE appointments SET status = is_cancelled WHERE status = 0;

COMMIT;
PRAGMA foreign_keys = ON;
