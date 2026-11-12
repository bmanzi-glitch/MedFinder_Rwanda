"""Create the DB and load demo data. Run: python seed.py"""
import os
from werkzeug.security import generate_password_hash
import app as a

if os.path.exists(a.DB_PATH):
    os.remove(a.DB_PATH)
a.init_db()

import sqlite3
c = sqlite3.connect(a.DB_PATH)
c.execute("PRAGMA foreign_keys = ON")
now = a.now_iso()

facilities = [
    ("Kimironko Pharmacy", "pharmacy", "Gasabo", "Kimironko"),
    ("Remera Health Center", "health_center", "Gasabo", "Remera"),
    ("Kacyiru Hospital Pharmacy", "hospital", "Gasabo", "Kacyiru"),
    ("Nyamirambo Pharmacy", "pharmacy", "Nyarugenge", "Nyamirambo"),
]
for f in facilities:
    c.execute("INSERT INTO facility(name,type,district,sector) VALUES (?,?,?,?)", f)

meds = [("Paracetamol", "500mg", "tablet"), ("Amoxicillin", "250mg", "capsule"),
        ("Quinine", "300mg", "tablet"), ("Oxytocin", "10IU", "injection"),
        ("Metformin", "500mg", "tablet")]
for m in meds:
    c.execute("INSERT INTO medicine(name,strength,form) VALUES (?,?,?)", m)

stock = [(1, 1, 120), (1, 2, 4), (1, 3, 0), (2, 1, 60), (2, 3, 25), (2, 4, 8),
         (3, 4, 30), (3, 5, 80), (4, 1, 0), (4, 2, 50)]
for fid, mid, q in stock:
    c.execute("INSERT INTO stock_record VALUES (?,?,?,?)", (fid, mid, q, now))
c.execute("INSERT INTO alert_threshold VALUES (1, 2, 10)")

# demo accounts (change PINs for any real use)
c.execute("INSERT INTO user(name,phone,pin_hash,role,job_title,facility_id) VALUES (?,?,?,?,?,?)",
          ("Demo Pharmacist", "0788000001", generate_password_hash("1234"), "staff", "Pharmacist", 1))
c.execute("INSERT INTO user(name,phone,pin_hash,role) VALUES (?,?,?,?)",
          ("Admin", "0788000000", generate_password_hash("admin1"), "admin"))
c.commit()
print("Seeded. Staff: 0788000001 / 1234   Admin: 0788000000 / admin1")