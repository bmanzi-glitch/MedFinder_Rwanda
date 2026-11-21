"""Give the demo facilities stock for EVERY medicine in the catalog.

Run from the project folder (venv active):

    python fill_demo_stock.py              # the 4 demo facilities only (ids 1-4)
    python fill_demo_stock.py --all        # every active facility in the database
    python fill_demo_stock.py --ids 1 5 9  # only these facility ids
    python fill_demo_stock.py --refresh    # also reset "last updated" to now, so stock is not "Unverified"
    python fill_demo_stock.py --reset      # overwrite quantities that already exist

By default a quantity that already exists is kept, so nothing you entered by hand is lost.
Quantities are random but repeatable: about 70% in stock, 15% low, 15% out of stock.
This is DEMO data only. Do not use it for a real pilot.
"""
import argparse
import random
import sqlite3

import app as a

DEMO_IDS = (1, 2, 3, 4)
# chance of (out, low) by facility type; the rest is in stock
ODDS = {"pharmacy": (0.15, 0.15), "health_center": (0.18, 0.17), "hospital": (0.08, 0.12)}


def quantity_for(rng, ftype):
    p_out, p_low = ODDS.get(ftype, (0.15, 0.15))
    r = rng.random()
    if r < p_out:
        return 0
    if r < p_out + p_low:
        return rng.randint(1, a.LOW_FRACTION_DEFAULT)
    return rng.randint(a.LOW_FRACTION_DEFAULT + 1, 300)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="every active facility")
    ap.add_argument("--ids", type=int, nargs="+", help="specific facility ids")
    ap.add_argument("--reset", action="store_true", help="overwrite existing quantities")
    ap.add_argument("--refresh", action="store_true", help="set last_updated to now on existing rows too")
    args = ap.parse_args()

    c = sqlite3.connect(a.DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")

    if args.all:
        facs = c.execute("SELECT * FROM facility WHERE is_active = 1 ORDER BY facility_id").fetchall()
    else:
        ids = args.ids or DEMO_IDS
        marks = ",".join("?" * len(ids))
        facs = c.execute(f"SELECT * FROM facility WHERE facility_id IN ({marks}) ORDER BY facility_id", ids).fetchall()
    meds = c.execute("SELECT medicine_id FROM medicine ORDER BY medicine_id").fetchall()
    if not facs or not meds:
        print("Nothing to do: no matching facilities or no medicines.")
        return

    # stock_history needs a user id; use the first admin (or any user)
    u = c.execute("SELECT user_id FROM user WHERE role='admin' ORDER BY user_id LIMIT 1").fetchone() \
        or c.execute("SELECT user_id FROM user ORDER BY user_id LIMIT 1").fetchone()
    uid = u["user_id"] if u else 0

    rng = random.Random(2026)          # fixed seed: same numbers every run
    now = a.now_iso()
    added = changed = kept = 0
    for f in facs:
        for m in meds:
            fid, mid = f["facility_id"], m["medicine_id"]
            q = quantity_for(rng, f["type"])          # drawn every time so results stay repeatable
            row = c.execute("SELECT quantity FROM stock_record WHERE facility_id=? AND medicine_id=?",
                            (fid, mid)).fetchone()
            if row is None:
                c.execute("INSERT INTO stock_record(facility_id, medicine_id, quantity, last_updated) VALUES (?,?,?,?)",
                          (fid, mid, q, now))
                c.execute("INSERT INTO stock_history(facility_id, medicine_id, quantity, user_id, updated_at) VALUES (?,?,?,?,?)",
                          (fid, mid, q, uid, now))
                added += 1
            elif args.reset:
                c.execute("UPDATE stock_record SET quantity=?, last_updated=? WHERE facility_id=? AND medicine_id=?",
                          (q, now, fid, mid))
                c.execute("INSERT INTO stock_history(facility_id, medicine_id, quantity, user_id, updated_at) VALUES (?,?,?,?,?)",
                          (fid, mid, q, uid, now))
                changed += 1
            elif args.refresh:
                c.execute("UPDATE stock_record SET last_updated=? WHERE facility_id=? AND medicine_id=?", (now, fid, mid))
                changed += 1
            else:
                kept += 1
    c.commit()
    print(f"{len(facs)} facilities x {len(meds)} medicines.  added {added}, updated {changed}, kept as they were {kept}.")
    for f in facs[:10]:
        n = c.execute("SELECT COUNT(*) FROM stock_record WHERE facility_id=?", (f["facility_id"],)).fetchone()[0]
        print(f"  {f['facility_id']:>4}  {f['name']}: {n} medicines in stock list")
    if len(facs) > 10:
        print(f"  ... and {len(facs) - 10} more")


if __name__ == "__main__":
    main()