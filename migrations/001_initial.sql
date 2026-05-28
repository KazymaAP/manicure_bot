-- migrations/001_initial.sql
-- Начальная схема базы данных Manicure Bot
-- Эта миграция соответствует схеме в src/infrastructure/database/connection.py

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;
PRAGMA cache_size = -8000;
PRAGMA temp_store = MEMORY;

-- ── Рабочие дни ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS working_days (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    date      TEXT    NOT NULL UNIQUE,   -- YYYY-MM-DD
    is_closed INTEGER NOT NULL DEFAULT 0 -- 0=открыт, 1=закрыт
);

CREATE INDEX IF NOT EXISTS idx_working_days_date ON working_days(date);

-- ── Слоты времени ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS time_slots (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    date      TEXT    NOT NULL,          -- YYYY-MM-DD (текстовый ключ)
    time      TEXT    NOT NULL,          -- HH:MM
    is_booked INTEGER NOT NULL DEFAULT 0,-- 0=свободен, 1=забронирован
    UNIQUE(date, time)
);

CREATE INDEX IF NOT EXISTS idx_time_slots_date      ON time_slots(date);
CREATE INDEX IF NOT EXISTS idx_time_slots_free      ON time_slots(date, is_booked);

-- ── Записи клиентов ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS appointments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    username      TEXT,
    client_name   TEXT    NOT NULL,
    phone         TEXT    NOT NULL,
    date          TEXT    NOT NULL,      -- YYYY-MM-DD
    time          TEXT    NOT NULL,      -- HH:MM
    created_at    TEXT    NOT NULL,      -- YYYY-MM-DD HH:MM:SS
    reminder_sent INTEGER NOT NULL DEFAULT 0,
    is_cancelled  INTEGER NOT NULL DEFAULT 0,
    comment       TEXT
);

CREATE INDEX IF NOT EXISTS idx_appointments_user_id ON appointments(user_id);
CREATE INDEX IF NOT EXISTS idx_appointments_date    ON appointments(date);
CREATE INDEX IF NOT EXISTS idx_appointments_active  ON appointments(user_id, is_cancelled);
