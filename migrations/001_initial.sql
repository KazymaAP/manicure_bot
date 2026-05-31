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
-- FIXED BUG 5: схема приведена к единому виду с connection.py (user_id INTEGER PRIMARY KEY)
CREATE TABLE IF NOT EXISTS blacklist (
    user_id    INTEGER PRIMARY KEY,
    reason     TEXT,
    created_at TEXT    NOT NULL          -- YYYY-MM-DD HH:MM:SS
);

-- Индекс не нужен — user_id уже PRIMARY KEY

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
-- FIXED архитектурное замечание: добавлено UNIQUE на name для соответствия connection.py
CREATE TABLE IF NOT EXISTS workday_templates (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL UNIQUE,  -- FIXED: добавлен UNIQUE как в connection.py
    slots      TEXT    NOT NULL,         -- JSON список временных слотов
    created_at TEXT    NOT NULL          -- YYYY-MM-DD HH:MM:SS
);

-- ── Бэкапы ────────────────────────────────────────────────────────────────
-- FIXED M-08: приведено к единому виду с connection.py (колонка path, не backup_path)
-- Это предотвращает расхождение схемы при деплое через миграцию и через initialize_schema()
CREATE TABLE IF NOT EXISTS backups (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    path       TEXT    NOT NULL,         -- FIXED: было backup_path — теперь соответствует connection.py
    created_at TEXT    NOT NULL          -- YYYY-MM-DD HH:MM:SS
);

-- ── Пользователи ────────────────────────────────────────────────────────────
-- FIXED: таблица всех пользователей для рассылки и статистики
CREATE TABLE IF NOT EXISTS users (
    user_id    INTEGER PRIMARY KEY,
    username   TEXT,
    first_name TEXT,
    last_name  TEXT,
    created_at TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id);
