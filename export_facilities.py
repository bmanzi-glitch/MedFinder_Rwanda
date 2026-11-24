"""Save the imported pharmacies (everything except demo facilities 1-4) to facilities_seed.csv."""
import csv
import sqlite3

import app as a

c = sqlite3.connect(a.DB_PATH)
c.row_factory = sqlite3.Row
cols = [r["name"] for r in c.execute("PRAGMA table_info(facility)") if r["name"] != "facility_id"]
rows = c.execute("SELECT * FROM facility WHERE facility_id > 4 ORDER BY facility_id").fetchall()
with open("facilities_seed.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(cols)
    for r in rows:
        w.writerow([r[k] for k in cols])
print(len(rows), "facilities saved to facilities_seed.csv")