"""Tests for the navigation, accounts, settings, directory, info pages and importers.

Run from the project folder:   python -m unittest discover -s tests -v
Uses a throw-away database, so your real medfinder.db is never touched.
"""
import csv
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

os.environ.setdefault("SECRET_KEY", "test-secret-key-used-only-by-unit-tests-123456")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as a                                          # noqa: E402
import import_medicines                                  # noqa: E402
import import_pharmacies                                 # noqa: E402
from werkzeug.security import check_password_hash, generate_password_hash  # noqa: E402


def iso(hours_ago=0):
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat(timespec="seconds")


class Part2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        a.DB_PATH = os.path.join(self.tmp.name, "test.db")
        a.init_db()
        c = sqlite3.connect(a.DB_PATH)
        c.executemany("INSERT INTO facility(name,type,district,sector,lat,lng,is_active) VALUES (?,?,?,?,?,?,?)", [
            ("Near Pharmacy", "pharmacy", "Gasabo", "Kimironko", -1.9487, 30.1262, 1),
            ("Far Health Center", "health_center", "Nyarugenge", "Nyamirambo", -1.9844, 30.0455, 1),
            ("Empty Pharmacy", "pharmacy", "Gasabo", "Remera", None, None, 1),
            ("Closed Pharmacy", "pharmacy", "Gasabo", "Kacyiru", None, None, 0)])
        c.execute("INSERT INTO medicine(name,strength,form,aliases) VALUES ('Paracetamol','500mg','tablet','Panadol')")
        c.executemany("INSERT INTO stock_record VALUES (?,?,?,?)", [(1, 1, 100, iso(1)), (2, 1, 50, iso(2))])
        c.execute("INSERT INTO user(name,phone,pin_hash,role,facility_id) VALUES (?,?,?,?,?)",
                  ("Staff One", "0788000001", generate_password_hash("1234"), "staff", 1))
        c.execute("INSERT INTO user(name,phone,pin_hash,role) VALUES (?,?,?,?)",
                  ("Admin", "0788000000", generate_password_hash("admin1"), "admin"))
        c.execute("INSERT INTO user(name,phone,pin_hash,role,lang) VALUES (?,?,?,?,?)",
                  ("Member", "0788222222", generate_password_hash("1234"), "user", "en"))
        c.commit()
        c.close()
        self.client = a.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    # helpers
    def token(self, client=None, path="/login"):
        client = client or self.client
        client.get(path)
        with client.session_transaction() as s:
            return s["csrf"]

    def login(self, phone, pin, client=None):
        client = client or self.client
        return client.post("/login", data={"phone": phone, "pin": pin, "csrf": self.token(client)})

    def rows(self, sql, *args):
        c = sqlite3.connect(a.DB_PATH)
        try:
            return c.execute(sql, args).fetchall()
        finally:
            c.close()

    GOOD = {"name": "Aline", "phone": "0788123456", "pin": "1234", "pin2": "1234", "agree": "on"}

    # ---------- sign up ----------
    def test_signup_creates_member_and_logs_in(self):
        data = dict(self.GOOD, phone="+250 788 123 456", csrf=self.token(path="/signup"))
        self.assertEqual(self.client.post("/signup", data=data).status_code, 302)
        self.assertEqual(self.rows("SELECT role, phone FROM user WHERE name='Aline'"), [("user", "0788123456")])
        with self.client.session_transaction() as s:
            self.assertEqual(s["role"], "user")

    def test_signup_rejects_bad_input(self):
        before = self.rows("SELECT COUNT(*) FROM user")[0][0]
        no_agree = {k: v for k, v in self.GOOD.items() if k != "agree"}
        cases = [dict(self.GOOD, phone="12345"), dict(self.GOOD, pin="12"), dict(self.GOOD, pin2="9999"),
                 dict(self.GOOD, name="  "), no_agree, dict(self.GOOD, phone="0788222222")]
        for bad in cases:
            bad["csrf"] = self.token(path="/signup")
            self.assertEqual(self.client.post("/signup", data=bad).status_code, 200, bad)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM user")[0][0], before)

    def test_signup_is_limited_per_connection(self):
        c = sqlite3.connect(a.DB_PATH)
        c.executemany("INSERT INTO login_attempt(phone, ip, attempted_at) VALUES ('signup','127.0.0.1',?)",
                      [(iso(),)] * a.SIGNUPS_PER_HOUR)
        c.commit()
        c.close()
        r = self.client.post("/signup", data=dict(self.GOOD, csrf=self.token(path="/signup")))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM user WHERE name='Aline'")[0][0], 0)

    def test_member_cannot_open_staff_or_admin_pages(self):
        self.assertEqual(self.login("0788222222", "1234").status_code, 302)
        self.assertEqual(self.client.get("/dashboard").status_code, 403)
        self.assertEqual(self.client.get("/admin").status_code, 403)
        self.assertEqual(self.client.get("/settings").status_code, 200)

    # ---------- settings ----------
    def test_settings_profile(self):
        self.login("0788222222", "1234")
        tok = self.token(path="/settings")
        self.client.post("/settings", data={"action": "profile", "name": "Aline B", "lang": "rw", "csrf": tok})
        self.assertEqual(self.rows("SELECT name, lang FROM user WHERE phone='0788222222'"), [("Aline B", "rw")])

    def test_settings_pin_change(self):
        self.login("0788222222", "1234")
        tok = self.token(path="/settings")
        self.client.post("/settings", data={"action": "pin", "current": "0000", "new": "5678", "new2": "5678", "csrf": tok})
        h = self.rows("SELECT pin_hash FROM user WHERE phone='0788222222'")[0][0]
        self.assertTrue(check_password_hash(h, "1234"))                     # wrong current PIN: unchanged
        self.client.post("/settings", data={"action": "pin", "current": "1234", "new": "5678", "new2": "5678", "csrf": tok})
        h = self.rows("SELECT pin_hash FROM user WHERE phone='0788222222'")[0][0]
        self.assertTrue(check_password_hash(h, "5678"))

    def test_only_members_can_delete_their_account(self):
        staff = a.app.test_client()
        self.login("0788000001", "1234", client=staff)
        tok = self.token(staff, "/settings")
        staff.post("/settings", data={"action": "delete", "current": "1234", "csrf": tok})
        self.assertEqual(self.rows("SELECT COUNT(*) FROM user WHERE phone='0788000001'")[0][0], 1)
        self.login("0788222222", "1234")
        tok = self.token(path="/settings")
        self.assertEqual(self.client.post("/settings", data={"action": "delete", "current": "1234", "csrf": tok}).status_code, 302)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM user WHERE phone='0788222222'")[0][0], 0)

    # ---------- directory ----------
    def test_directory_lists_active_facilities_with_stock_first(self):
        html = self.client.get("/facilities").get_data(as_text=True)
        self.assertNotIn("Closed Pharmacy", html)
        self.assertLess(html.index("<h3>Near Pharmacy</h3>"), html.index("<h3>Empty Pharmacy</h3>"))

    def test_directory_filters_and_pages(self):
        html = self.client.get("/facilities?q=empty").get_data(as_text=True)
        self.assertIn("<h3>Empty Pharmacy</h3>", html)
        self.assertNotIn("<h3>Near Pharmacy</h3>", html)
        html = self.client.get("/facilities?type=health_center").get_data(as_text=True)
        self.assertIn("<h3>Far Health Center</h3>", html)
        self.assertNotIn("<h3>Near Pharmacy</h3>", html)
        old = a.PAGE_SIZE
        a.PAGE_SIZE = 1
        try:
            p1 = self.client.get("/facilities").get_data(as_text=True)
            p2 = self.client.get("/facilities?page=2").get_data(as_text=True)
            p99 = self.client.get("/facilities?page=99").get_data(as_text=True)
        finally:
            a.PAGE_SIZE = old
        self.assertIn("<h3>Far Health Center</h3>", p1)
        self.assertNotIn("<h3>Near Pharmacy</h3>", p1)
        self.assertIn("<h3>Near Pharmacy</h3>", p2)
        self.assertIn("<h3>Empty Pharmacy</h3>", p99)

    def test_facility_page(self):
        self.assertIn("Paracetamol", self.client.get("/facility/1").get_data(as_text=True))
        self.assertIn("has not reported any stock", self.client.get("/facility/3").get_data(as_text=True))
        self.assertEqual(self.client.get("/facility/4").status_code, 404)       # inactive
        self.assertEqual(self.client.get("/facility/999").status_code, 404)
        self.assertEqual(self.client.get("/facility/1?lang=rw").status_code, 200)

    def test_language_links_work_on_facility_and_error_pages(self):
        self.assertIn("/facility/1?lang=rw", self.client.get("/facility/1").get_data(as_text=True))
        r = self.client.get("/nope?lang=rw")
        self.assertEqual(r.status_code, 404)
        self.assertIn("Urupapuro ntirubonetse", r.get_data(as_text=True))

    def test_api_facilities(self):
        data = self.client.get("/api/facilities").get_json()
        self.assertEqual(data["count"], 3)
        self.assertIn("OpenStreetMap", data["attribution"])

    # ---------- information pages, footer, contact ----------
    def test_info_pages_in_both_languages(self):
        for slug in ("about", "faq", "privacy", "terms"):
            for lang in ("en", "rw"):
                self.assertEqual(self.client.get(f"/{slug}?lang={lang}").status_code, 200, (slug, lang))

    def test_footer_and_navigation(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("OpenStreetMap", html)
        for href in ('href="/facilities"', 'href="/signup"', 'href="/privacy"', 'href="/terms"'):
            self.assertIn(href, html)

    def test_contact_page_hidden_until_configured(self):
        old = dict(a.CONTACT)
        try:
            a.CONTACT.update(email="", phone="", address="")
            self.assertEqual(self.client.get("/contact").status_code, 404)
            a.CONTACT["email"] = "help@example.org"
            self.assertIn("help@example.org", self.client.get("/contact").get_data(as_text=True))
        finally:
            a.CONTACT.update(old)

    def test_normalize_phone(self):
        for raw in ("+250 788 123 456", "250788123456", "0788 123 456", "0788-123-456"):
            self.assertEqual(a.normalize_phone(raw), "0788123456", raw)

    # ---------- medicine importer ----------
    def test_starter_list_is_clean(self):
        with open(os.path.join(a.BASE, "medicines_starter.csv"), newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        self.assertEqual(reader.fieldnames, ["name", "strength", "form", "aliases"])
        self.assertGreaterEqual(len(rows), 140)
        keys = [import_medicines.key(r["name"], r["strength"], r["form"]) for r in rows]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(all(r["name"].strip() for r in rows))

    def test_import_medicines_skips_existing(self):
        path = os.path.join(self.tmp.name, "meds.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["name", "strength", "form", "aliases"])
            w.writerows([["paracetamol", "500MG", "Tablet", "dup of an existing one"],
                         ["Newdrug", "10mg", "tablet", "Brand"], ["Otherdrug", "", "syrup", ""],
                         ["Newdrug", "10mg", "tablet", ""], ["", "", "", ""]])
        c = sqlite3.connect(a.DB_PATH)
        self.assertEqual(import_medicines.import_file(c, path, dry_run=True), (2, 2))
        self.assertEqual(c.execute("SELECT COUNT(*) FROM medicine").fetchone()[0], 1)    # dry run saved nothing
        self.assertEqual(import_medicines.import_file(c, path), (2, 2))
        self.assertEqual(import_medicines.import_file(c, path), (0, 4))
        c.close()
        self.assertEqual(self.rows("SELECT COUNT(*) FROM medicine")[0][0], 3)

    # ---------- pharmacy importer ----------
    ELEMENTS = [
        {"type": "node", "id": 1, "lat": -1.95, "lon": 30.10,
         "tags": {"amenity": "pharmacy", "name": "Test Pharmacy One", "phone": "+250 788 111 222; +250 788 333 444",
                  "opening_hours": "Mo-Su 08:00-20:00", "addr:suburb": "Remera"}},
        {"type": "way", "id": 5, "center": {"lat": -1.94, "lon": 30.08}, "tags": {"amenity": "hospital", "name": "Test Hospital"}},
        {"type": "node", "id": 2, "lat": -1.95, "lon": 30.10, "tags": {"amenity": "clinic"}},                 # no name
        {"type": "node", "id": 3, "lat": 48.0, "lon": 2.0, "tags": {"amenity": "pharmacy", "name": "Paris"}},  # not Rwanda
        {"type": "node", "id": 4, "lat": -1.95, "lon": 30.10, "tags": {"amenity": "bank", "name": "Bank"}}]    # wrong kind

    def test_parse_pharmacies(self):
        rows, skipped = import_pharmacies.parse_elements(self.ELEMENTS, "Gasabo")
        self.assertEqual([r["name"] for r in rows], ["Test Pharmacy One", "Test Hospital"])
        self.assertEqual(rows[0]["phone"], "+250 788 111 222")
        self.assertEqual(rows[0]["sector"], "Remera")
        self.assertEqual((rows[1]["type"], rows[1]["osm_id"]), ("hospital", "way/5"))
        self.assertEqual(sum(skipped.values()), 3)

    def test_save_pharmacies_skips_duplicates(self):
        rows, _ = import_pharmacies.parse_elements(self.ELEMENTS, "Gasabo")
        rows.append({"osm_id": "node/99", "name": "near pharmacy", "type": "pharmacy", "district": "Gasabo",
                     "sector": None, "lat": -1.9, "lng": 30.1, "phone": None, "hours": None})   # same as a hand-made one
        c = sqlite3.connect(a.DB_PATH)
        self.assertEqual(import_pharmacies.save(c, rows), (2, 1))
        self.assertEqual(import_pharmacies.save(c, rows), (0, 3))
        c.close()
        self.assertIn("Test Pharmacy One", self.client.get("/facilities").get_data(as_text=True))
        self.assertNotIn("Test Pharmacy One", self.client.get("/?q=paracetamol").get_data(as_text=True))  # no stock yet

    def test_area_query_rejects_odd_names(self):
        self.assertIn("Gasabo", import_pharmacies.build_area_query("Gasabo"))
        with self.assertRaises(ValueError):
            import_pharmacies.build_area_query('Ga"sabo')


if __name__ == "__main__":
    unittest.main()