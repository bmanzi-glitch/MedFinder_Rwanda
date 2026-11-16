"""Import pharmacies, clinics and hospitals from OpenStreetMap into the facility table.

   python import_pharmacies.py --dry-run          look first, change nothing (do this first)
   python import_pharmacies.py                    import for Gasabo, Kicukiro and Nyarugenge (Kigali)
   python import_pharmacies.py --districts Huye,Musanze
   python import_pharmacies.py --bbox S,W,N,E --district Gasabo     fallback, see below
   python import_pharmacies.py --from-file saved.json --district Gasabo

Data comes from OpenStreetMap contributors (ODbL licence). The site footer credits them.
Coverage in OpenStreetMap is incomplete, so expect to find fewer places than really exist.

If a district name finds nothing (the name in OpenStreetMap may be spelled differently), use the
fallback: give a bounding box (south,west,north,east in decimal degrees, taken from
openstreetmap.org) and the district name to store for everything found inside it.

Facilities are saved with no stock. They show in the Pharmacies directory, and in the medicine search
only after their staff report stock. A place already imported (same OSM id) or already registered by hand
(same name and district) is skipped.
"""
import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime

import migrate

DB_PATH = migrate.DB_PATH
ENDPOINTS = ["https://overpass-api.de/api/interpreter",
             "https://overpass.private.coffee/api/interpreter",
             "https://overpass.kumi.systems/api/interpreter"]
USER_AGENT = "MedFinderRwanda-importer/1.0 (b.manzi@alustudent.com)"
TYPE_MAP = {"pharmacy": "pharmacy", "hospital": "hospital", "clinic": "health_center"}
AMENITIES = "|".join(TYPE_MAP)
LAT_RANGE, LNG_RANGE = (-3.0, -1.0), (28.8, 31.0)      # Rwanda, used to drop wrong coordinates
NAME_OK = re.compile(r"^[A-Za-z' -]{2,40}$")


def build_area_query(name):
    if not NAME_OK.match(name):
        raise ValueError(f"Unusual district name: {name!r}")
    # The bounding box limits the search to Rwanda, which makes the name lookup fast.
    box = f"({LAT_RANGE[0]},{LNG_RANGE[0]},{LAT_RANGE[1]},{LNG_RANGE[1]})"
    return (f'[out:json][timeout:60];\n'
            f'rel["boundary"="administrative"]["name"~"^{name}( District)?$",i]{box};\n'
            f'map_to_area->.d;\n'
            f'nwr["amenity"~"^({AMENITIES})$"](area.d);\nout center tags;')

def build_bbox_query(s, w, n, e):
    return (f'[out:json][timeout:90];\n'
            f'nwr["amenity"~"^({AMENITIES})$"]({s},{w},{n},{e});\nout center tags;')

def fetch(query):
    body = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for attempt in range(3):
        if attempt:
            wait = 15 * attempt
            print(f"All servers busy. Waiting {wait} seconds, then trying again...", flush=True)
            time.sleep(wait)
        for url in ENDPOINTS:
            print(f"Asking {url.split('/')[2]} (up to 75 seconds)...", flush=True)
            try:
                req = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=75) as resp:
                    return json.load(resp).get("elements", [])
            except (urllib.error.URLError, OSError, ValueError) as err:
                print(f"  No answer: {err}", flush=True)
                last = err
    sys.exit(f"Could not reach OpenStreetMap (Overpass): {last}\nThe free servers are busy. Try again later, or use the manual file method.")

def clean_phone(raw):
    return (raw or "").split(";")[0].strip()[:30] or None
HOSPITAL_WORDS = re.compile(r"hospital|hôpital|hopital|ibitaro|chuk|chub|referral", re.I)
NOT_MEDICAL = re.compile(r"optical|optic|dental|dentist|salon|spa\b|cosmetic", re.I)

def parse_elements(elements, district):
    """Turn Overpass elements into facility rows. Returns (rows, skipped) where skipped counts reasons."""
    rows, skipped = [], Counter()
    for el in elements:
        tags = el.get("tags") or {}
        ftype = TYPE_MAP.get(tags.get("amenity"))
        name = (tags.get("name") or tags.get("name:en") or "").strip()
        if ftype == "hospital" and not HOSPITAL_WORDS.search(name):
            ftype = "health_center"          # many clinics are tagged as hospitals in OpenStreetMap
        if NOT_MEDICAL.search(name):
            ftype = None                     # optical shops and dental or beauty places are not pharmacies or clinics
        lat, lng = el.get("lat"), el.get("lon")
        if lat is None:
            c = el.get("center") or {}
            lat, lng = c.get("lat"), c.get("lon")
        if not ftype:
            skipped["not a pharmacy, clinic or hospital"] += 1
        elif not name:
            skipped["no name"] += 1
        elif lat is None or lng is None or not (LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LNG_RANGE[0] <= lng <= LNG_RANGE[1]):
            skipped["no usable location"] += 1
        else:
            rows.append({
                "osm_id": f"{el.get('type', 'node')}/{el.get('id')}",
                "name": name[:120], "type": ftype, "district": district,
                "sector": (tags.get("addr:suburb") or tags.get("addr:neighbourhood") or "").strip()[:60] or None,
                "lat": round(lat, 6), "lng": round(lng, 6),
                "phone": clean_phone(tags.get("phone") or tags.get("contact:phone")),
                "hours": (tags.get("opening_hours") or "").strip()[:120] or None})
    return rows, skipped


def save(conn, rows):
    """Insert new facilities. Returns (added, duplicates)."""
    added = dup = 0
    for r in rows:
        if conn.execute("SELECT 1 FROM facility WHERE osm_id=?", (r["osm_id"],)).fetchone() or \
           conn.execute("SELECT 1 FROM facility WHERE lower(name)=lower(?) AND lower(district)=lower(?)",
                        (r["name"], r["district"])).fetchone():
            dup += 1
            continue
        conn.execute("""INSERT INTO facility(name,type,district,sector,lat,lng,phone,opening_hours,osm_id)
                        VALUES (?,?,?,?,?,?,?,?,?)""",
                     (r["name"], r["type"], r["district"], r["sector"], r["lat"], r["lng"],
                      r["phone"], r["hours"], r["osm_id"]))
        added += 1
    conn.commit()
    return added, dup


def main(argv=None):
    p = argparse.ArgumentParser(description="Import facilities from OpenStreetMap.")
    p.add_argument("--dry-run", action="store_true", help="show what would be imported, change nothing")
    p.add_argument("--districts", default="Gasabo,Kicukiro,Nyarugenge")
    p.add_argument("--bbox", help="fallback: south,west,north,east")
    p.add_argument("--district", help="district name to store (needed with --bbox or --from-file)")
    p.add_argument("--from-file", help="read a saved Overpass JSON file instead of the internet")
    args = p.parse_args(argv)

    batches = []
    if args.from_file:
        if not args.district:
            sys.exit("--from-file needs --district")
        with open(args.from_file, encoding="utf-8") as f:
            data = json.load(f)
        batches.append((args.district, data["elements"] if isinstance(data, dict) else data))
    elif args.bbox:
        if not args.district:
            sys.exit("--bbox needs --district")
        try:
            s, w, n, e = [float(x) for x in args.bbox.split(",")]
        except ValueError:
            sys.exit("--bbox must be four numbers: south,west,north,east")
        batches.append((args.district, fetch(build_bbox_query(s, w, n, e))))
    else:
        names = [d.strip() for d in args.districts.split(",") if d.strip()]
        for i, name in enumerate(names):
            if i:
                time.sleep(5)                      # be polite to the free Overpass servers
            els = fetch(build_area_query(name))
            if not els:
                print(f"Warning: nothing found for district '{name}'. Its OpenStreetMap name may differ. "
                      f"Try the fallback: --bbox S,W,N,E --district {name}")
            batches.append((name, els))

    rows, skipped = [], Counter()
    for district, els in batches:
        r, s = parse_elements(els, district)
        print(f"{district}: {len(els)} found, {len(r)} usable")
        rows += r
        skipped.update(s)
    print("By type:", dict(Counter(r["type"] for r in rows)))
    for why, n in skipped.items():
        print(f"Skipped {n}: {why}")

    if args.dry_run:
        for r in rows[:15]:
            print(f"  {r['type']:<13} {r['district']:<11} {r['name']}")
        print("Dry run: nothing was saved.")
        return
    if os.path.exists(DB_PATH):
        backup = f"{DB_PATH}.bak-{datetime.now():%Y%m%d-%H%M%S}"
        shutil.copy2(DB_PATH, backup)
        print(f"Backup saved: {backup}")
    conn = sqlite3.connect(DB_PATH)
    migrate.add_missing(conn)
    added, dup = save(conn, rows)
    conn.close()
    print(f"Added {added} facilities, skipped {dup} that already exist.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nStopped.")