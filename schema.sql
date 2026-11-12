-- MedFinder Rwanda schema (mirrors SRS Appendix B.3 class diagram)
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS facility (
    facility_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL CHECK (type IN ('pharmacy','health_center','hospital')),
    district    TEXT NOT NULL,
    sector      TEXT,
    lat         REAL,
    lng         REAL,
    is_active   INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS user (
    user_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    phone       TEXT NOT NULL UNIQUE,
    pin_hash    TEXT NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('staff','admin')),
    job_title   TEXT,
    facility_id INTEGER REFERENCES facility(facility_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS medicine (
    medicine_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    strength    TEXT,
    form        TEXT,
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
    medicine_id     INTEGER NOT NULL,
    message         TEXT NOT NULL,
    sent_at         TEXT NOT NULL,
    delivery_status TEXT NOT NULL DEFAULT 'pending'
);

-- NFR 11: no personal data, only query text and district
CREATE TABLE IF NOT EXISTS search_request (
    request_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    channel     TEXT NOT NULL,
    query_text  TEXT NOT NULL,
    district    TEXT,
    received_at TEXT NOT NULL
);