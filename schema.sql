-- MedFinder Rwanda schema (mirrors SRS Appendix B.3 class diagram)
-- Every statement is CREATE ... IF NOT EXISTS, so the app can run this file safely on every start.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS facility (
    facility_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL CHECK (type IN ('pharmacy','health_center','hospital')),
    district    TEXT NOT NULL,
    sector      TEXT,
    lat         REAL,
    lng         REAL,
    is_active   INTEGER NOT NULL DEFAULT 1,
    phone       TEXT,
    opening_hours TEXT,
    osm_id      TEXT                       -- set for facilities imported from OpenStreetMap, e.g. node/12345
);

CREATE TABLE IF NOT EXISTS user (
    user_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    phone       TEXT NOT NULL UNIQUE,
    pin_hash    TEXT NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('staff','admin','manager','user')),   -- 'user' = a normal member of the public
    job_title   TEXT,
    facility_id INTEGER REFERENCES facility(facility_id) ON DELETE CASCADE,
    lang        TEXT                       -- preferred language: en or rw
);

CREATE TABLE IF NOT EXISTS medicine (
    medicine_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    strength    TEXT,
    form        TEXT,
    aliases     TEXT,                      -- other names people search for, e.g. brands: "Panadol, Doliprane"
    UNIQUE (name, strength, form)
);

CREATE TABLE IF NOT EXISTS stock_record (
    facility_id  INTEGER NOT NULL REFERENCES facility(facility_id) ON DELETE CASCADE,
    medicine_id  INTEGER NOT NULL REFERENCES medicine(medicine_id),
    quantity     INTEGER NOT NULL CHECK (quantity >= 0),
    last_updated TEXT NOT NULL,
    PRIMARY KEY (facility_id, medicine_id)
);

-- FR 2.3 / NFR 10: audit trail of every stock update
CREATE TABLE IF NOT EXISTS stock_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    facility_id INTEGER NOT NULL,
    medicine_id INTEGER NOT NULL,
    quantity    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alert_threshold (
    facility_id INTEGER NOT NULL REFERENCES facility(facility_id) ON DELETE CASCADE,
    medicine_id INTEGER NOT NULL REFERENCES medicine(medicine_id),
    min_quantity INTEGER NOT NULL,
    PRIMARY KEY (facility_id, medicine_id)
);

CREATE TABLE IF NOT EXISTS alert (
    alert_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    facility_id     INTEGER NOT NULL,
    medicine_id     INTEGER,               -- empty for 'stale' reminders, which are about the facility
    message         TEXT NOT NULL,
    sent_at         TEXT NOT NULL,
    delivery_status TEXT NOT NULL DEFAULT 'pending',
    kind            TEXT NOT NULL DEFAULT 'low'
);

-- NFR 11: no personal data, only query text and district
CREATE TABLE IF NOT EXISTS search_request (
    request_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    channel     TEXT NOT NULL,
    query_text  TEXT NOT NULL,
    district    TEXT,
    received_at TEXT NOT NULL,
    result_count INTEGER
);

-- patient feedback: did the patient find the medicine? (used by /feedback and the admin accuracy report)
CREATE TABLE IF NOT EXISTS feedback (
    feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
    facility_id INTEGER NOT NULL,
    medicine_id INTEGER NOT NULL,
    found INTEGER NOT NULL,
    status_shown TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (facility_id) REFERENCES facility(facility_id),
    FOREIGN KEY (medicine_id) REFERENCES medicine(medicine_id)
);

-- failed logins and recent sign-ups, used to slow down PIN guessing and mass account creation.
-- A successful login clears that phone's rows.
CREATE TABLE IF NOT EXISTS login_attempt (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    phone        TEXT NOT NULL,
    ip           TEXT NOT NULL,
    attempted_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_login_attempt_phone ON login_attempt(phone, attempted_at);
CREATE INDEX IF NOT EXISTS idx_login_attempt_ip ON login_attempt(ip, attempted_at);