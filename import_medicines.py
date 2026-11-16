"""Load medicines from a CSV file into the catalog.

   python import_medicines.py                 loads medicines_starter.csv
   python import_medicines.py my_list.csv     loads your own file
   python import_medicines.py --dry-run       shows what would be added and changes nothing

The first row of the CSV is the header: name,strength,form,aliases
Strength, form and aliases may be empty. A medicine already in the catalog (same name, strength and
form, ignoring capital letters) is skipped, so it is safe to run this more than once.
"""
import csv
import os
import shutil
import sqlite3
import sys
from datetime import datetime

import migrate

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = migrate.DB_PATH
DEFAULT_CSV = os.path.join(BASE, "medicines_starter.csv")


def key(name, strength, form):
    return (name.strip().lower(), (strength or "").strip().lower(), (form or "").strip().lower())


def import_file(conn, path, dry_run=False):
    """Returns (added, skipped). Blank rows are ignored."""
    seen = {key(n, s, f) for n, s, f in
            conn.execute("SELECT name, coalesce(strength,''), coalesce(form,'') FROM medicine")}
    added = skipped = 0
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            name = (row.get("name") or "").strip()
            if not name:
                continue
            strength = (row.get("strength") or "").strip()
            form = (row.get("form") or "").strip()
            aliases = (row.get("aliases") or "").strip()
            k = key(name, strength, form)
            if k in seen:
                skipped += 1
                continue
            seen.add(k)
            if not dry_run:
                conn.execute("INSERT INTO medicine(name,strength,form,aliases) VALUES (?,?,?,?)",
                             (name, strength, form, aliases or None))
            added += 1
    if not dry_run:
        conn.commit()
    return added, skipped


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    path = args[0] if args else DEFAULT_CSV
    if not os.path.exists(path):
        sys.exit(f"File not found: {path}")
    if not dry and os.path.exists(DB_PATH):
        backup = f"{DB_PATH}.bak-{datetime.now():%Y%m%d-%H%M%S}"
        shutil.copy2(DB_PATH, backup)
        print(f"Backup saved: {backup}")
    conn = sqlite3.connect(DB_PATH)
    migrate.add_missing(conn)
    added, skipped = import_file(conn, path, dry_run=dry)
    conn.close()
    print(f"{'Would add' if dry else 'Added'} {added} medicines, skipped {skipped} that already exist.")


if __name__ == "__main__":
    main()