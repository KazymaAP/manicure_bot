-- migrations/002_add_fk_time_slots.sql
-- FIXED BUG-C3: SQLite не поддерживает ADD CONSTRAINT через ALTER TABLE.
-- Для добавления FOREIGN KEY необходимо пересоздать таблицу с новой схемой.
-- Этот скрипт выполняет безопасное пересоздание time_slots с сохранением данных.
-- ВАЖНО: убедитесь что PRAGMA foreign_keys=ON установлен перед выполнением.

PRAGMA foreign_keys = OFF;
BEGIN TRANSACTION;

-- Создаём новую таблицу time_slots с FOREIGN KEY
CREATE TABLE IF NOT EXISTS time_slots_new (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    date      TEXT    NOT NULL,
    time      TEXT    NOT NULL,
    is_booked INTEGER NOT NULL DEFAULT 0,
    UNIQUE(date, time),
    FOREIGN KEY (date) REFERENCES working_days(date) ON DELETE CASCADE
);

-- Переносим данные (date без FOREIGN KEY → только даты из working_days)
INSERT OR IGNORE INTO time_slots_new (id, date, time, is_booked)
SELECT ts.id, ts.date, ts.time, ts.is_booked
FROM time_slots ts
WHERE EXISTS (SELECT 1 FROM working_days wd WHERE wd.date = ts.date);

-- Удаляем старую таблицу и индексы
DROP TABLE IF EXISTS time_slots;

-- Переименовываем новую таблицу
ALTER TABLE time_slots_new RENAME TO time_slots;

-- Восстанавливаем индексы
CREATE INDEX IF NOT EXISTS idx_time_slots_date ON time_slots(date);
CREATE INDEX IF NOT EXISTS idx_time_slots_free ON time_slots(date, is_booked);

COMMIT;
PRAGMA foreign_keys = ON;
