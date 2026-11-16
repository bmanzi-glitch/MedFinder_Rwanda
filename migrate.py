"""Upgrade an existing MedFinder database in place.

Run it once from the project folder:   python migrate.py
It saves a timestamped backup first, and it is safe to run again: it only changes what is missing.
The app also calls add_missing() on start-up, so new tables and columns appear on their own.
"""
import os
import shutil
import sqlite3
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("MEDFINDER_DB", os.path.join(BASE, "medfinder.db"))


def _info(conn, table):
    return list(conn.execute(f"PRAGMA table_info({table})"))


def add_missing(conn):
    """Additive upgrades only: new tables and columns. Never removes or rewrites data."""
    with open(os.path.join(BASE, "schema.sql")) as f:
        conn.executescript(f.read())          # every statement is CREATE ... IF NOT EXISTS
    for table, column, ddl in (("medicine", "aliases", "TEXT"),
                               ("search_request", "result_count", "INTEGER"),
                               ("alert", "kind", "TEXT NOT NULL DEFAULT 'low'"),
                               ("facility", "phone", "TEXT"),
                               ("facility", "opening_hours", "TEXT"),
                               ("facility", "osm_id", "TEXT"),
                               ("user", "lang", "TEXT")):
        if column not in [r[1] for r in _info(conn, table)]:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
            except sqlite3.OperationalError as err:      # another worker got there first
                if "duplicate column" not in str(err):
                    raise
    # one OpenStreetMap place can only be imported once (empty osm_id values are allowed many times)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_facility_osm ON facility(osm_id)")
    conn.commit()


def rebuild_tables(conn):
    """Changes SQLite cannot make in place. Needs a connection opened with isolation_level=None.
    1. alert.medicine_id may be empty (a 'stale' reminder is about the facility, not a medicine).
    2. user.role may be 'manager' (the admin page already offers it) or 'user' (members of the public)."""
    conn.execute("PRAGMA foreign_keys = OFF")
    changed = []

    if any(r[1] == "medicine_id" and r[3] == 1 for r in _info(conn, "alert")):
        conn.execute("BEGIN")
        conn.execute("""CREATE TABLE alert_new (
            alert_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            facility_id     INTEGER NOT NULL,
            medicine_id     INTEGER,
            message         TEXT NOT NULL,
            sent_at         TEXT NOT NULL,
            delivery_status TEXT NOT NULL DEFAULT 'pending',
            kind            TEXT NOT NULL DEFAULT 'low')""")
        conn.execute("""INSERT INTO alert_new(alert_id, facility_id, medicine_id, message, sent_at, delivery_status, kind)
                        SELECT alert_id, facility_id, medicine_id, message, sent_at, delivery_status, kind FROM alert""")
        conn.execute("DROP TABLE alert")
        conn.execute("ALTER TABLE alert_new RENAME TO alert")
        conn.execute("COMMIT")
        changed.append("alert")

    user_sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'user'").fetchone()[0]
    if "'user'" not in user_sql:
        conn.execute("BEGIN")
        conn.execute("""CREATE TABLE user_new (
            user_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            phone       TEXT NOT NULL UNIQUE,
            pin_hash    TEXT NOT NULL,
            role        TEXT NOT NULL CHECK (role IN ('staff','admin','manager','user')),
            job_title   TEXT,
            facility_id INTEGER REFERENCES facility(facility_id) ON DELETE CASCADE,
            lang        TEXT)""")
        conn.execute("""INSERT INTO user_new(user_id, name, phone, pin_hash, role, job_title, facility_id, lang)
                        SELECT user_id, name, phone, pin_hash, role, job_title, facility_id, lang FROM user""")
        conn.execute("DROP TABLE user")
        conn.execute("ALTER TABLE user_new RENAME TO user")
        conn.execute("COMMIT")
        changed.append("user")

    conn.execute("PRAGMA foreign_keys = ON")
    return changed


def main():
    if not os.path.exists(DB_PATH):
        sys.exit(f"No database at {DB_PATH}. Nothing to upgrade. Run python seed.py for a new demo database.")
    backup = f"{DB_PATH}.bak-{datetime.now():%Y%m%d-%H%M%S}"
    shutil.copy2(DB_PATH, backup)
    print(f"Backup saved: {backup}")

    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    add_missing(conn)
    changed = rebuild_tables(conn)
    problems = conn.execute("PRAGMA integrity_check").fetchall() + conn.execute("PRAGMA foreign_key_check").fetchall()
    conn.close()
    if problems != [("ok",)]:
        print("Check these before going live:", problems)
    print("Rebuilt tables:", ", ".join(changed) if changed else "none needed")
    print("Done.")


if __name__ == "__main__":
    main()