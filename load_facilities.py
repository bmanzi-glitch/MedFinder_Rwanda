"""Load facilities from facilities_seed.csv (skips ones that already exist)."""
import csv
import os
import sqlite3

import app as a

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "facilities_seed.csv")
if not os.path.exists(path):
    print("facilities_seed.csv not found, skipping")
    raise SystemExit

c = sqlite3.connect(a.DB_PATH)
table_cols = {r[1] for r in c.execute("PRAGMA table_info(facility)")}
added = 0
with open(path, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        cols = [k for k in row if k in table_cols]
        exists = c.execute(
            "SELECT 1 FROM facility WHERE name=? AND IFNULL(district,'')=?",
            (row.get("name"), row.get("district") or ""),
        ).fetchone()
        if exists:
            continue
        vals = [row[k] if row[k] != "" else None for k in cols]
        c.execute(
            f"INSERT INTO facility({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals
        )
        added += 1
c.commit()
print(f"{added} facilities loaded from facilities_seed.csv")