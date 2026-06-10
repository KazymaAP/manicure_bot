-- Migration 006: Add index on appointments.date for performance
-- FIXED БАГ #24: таблица appointments не имела составного индекса по (date, is_cancelled),
-- хотя эти поля активно используются для фильтрации:
--   WHERE date = ? AND is_cancelled = 0
--   WHERE date BETWEEN ? AND ?
--   WHERE user_id = ? AND is_cancelled = 0

CREATE INDEX IF NOT EXISTS idx_appointments_date ON appointments (date, is_cancelled);
CREATE INDEX IF NOT EXISTS idx_appointments_user_active ON appointments (user_id, is_cancelled);
