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
    comment       TEXT,
    service       TEXT                   -- FIXED: тип услуги (добавлено в v4)
);

CREATE INDEX IF NOT EXISTS idx_appointments_user_id ON appointments(user_id);
CREATE INDEX IF NOT EXISTS idx_appointments_date    ON appointments(date);
CREATE INDEX IF NOT EXISTS idx_appointments_active  ON appointments(user_id, is_cancelled);

-- ── Чёрный список (блокировка пользователей) ──────────────────────────────
-- FIXED: добавлена таблица для блокировки пользователей
CREATE TABLE IF NOT EXISTS blacklist (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL UNIQUE,
    reason     TEXT,
    created_at TEXT    NOT NULL          -- YYYY-MM-DD HH:MM:SS
);

CREATE INDEX IF NOT EXISTS idx_blacklist_user_id ON blacklist(user_id);

-- ── Лист ожидания ─────────────────────────────────────────────────────────
-- FIXED: добавлена таблица для листа ожидания
CREATE TABLE IF NOT EXISTS waitlist (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    date       TEXT    NOT NULL,         -- YYYY-MM-DD
    created_at TEXT    NOT NULL,         -- YYYY-MM-DD HH:MM:SS
    UNIQUE(user_id, date)
);

CREATE INDEX IF NOT EXISTS idx_waitlist_date    ON waitlist(date);
CREATE INDEX IF NOT EXISTS idx_waitlist_user_id ON waitlist(user_id);

-- ── Шаблоны расписания ────────────────────────────────────────────────────
-- FIXED: добавлена таблица для шаблонов рабочих дней
CREATE TABLE IF NOT EXISTS workday_templates (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    slots      TEXT    NOT NULL,         -- JSON список временных слотов
    created_at TEXT    NOT NULL          -- YYYY-MM-DD HH:MM:SS
);

-- ── Бэкапы ────────────────────────────────────────────────────────────────
-- FIXED: добавлена таблица для отслеживания бэкапов (опционально)
CREATE TABLE IF NOT EXISTS backups (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    backup_path TEXT    NOT NULL,
    created_at TEXT    NOT NULL,         -- YYYY-MM-DD HH:MM:SS
    size_bytes INTEGER                   -- Размер бэкапа в байтах
);
