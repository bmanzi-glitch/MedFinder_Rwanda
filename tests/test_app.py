"""Automated tests for MedFinder Rwanda.

Run from the project folder:   python -m unittest discover -s tests -v
Uses a throw-away database, so your real medfinder.db is never touched.
"""
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

os.environ.setdefault("SECRET_KEY", "test-secret-key-used-only-by-unit-tests-123456")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as a                                   # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402


def iso(hours_ago=0):
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat(timespec="seconds")


class MedFinderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        a.DB_PATH = os.path.join(self.tmp.name, "test.db")
        a.init_db()
        c = sqlite3.connect(a.DB_PATH)
        # id1 near Kimironko, id2 farther away, id3 has no coordinates
        c.executemany("INSERT INTO facility(name,type,district,sector,lat,lng) VALUES (?,?,?,?,?,?)", [
            ("Near Pharmacy", "pharmacy", "Gasabo", "Kimironko", -1.9487, 30.1262),
            ("Far Health Center", "health_center", "Nyarugenge", "Nyamirambo", -1.9844, 30.0455),
            ("No Map Hospital", "hospital", "Gasabo", "Kacyiru", None, None)])
        c.executemany("INSERT INTO medicine(name,strength,form,aliases) VALUES (?,?,?,?)", [
            ("Paracetamol", "500mg", "tablet", "Panadol, Doliprane"),
            ("Amoxicillin", "250mg", "capsule", "Amoxil")])
        c.executemany("INSERT INTO stock_record VALUES (?,?,?,?)", [
            (1, 1, 100, iso(1)), (2, 1, 50, iso(2)), (3, 1, 0, iso(1)),
            (1, 2, 40, iso(80))])                                   # 80 hours old => Unverified
        c.execute("INSERT INTO user(name,phone,pin_hash,role,facility_id) VALUES (?,?,?,?,?)",
                  ("Staff One", "0788000001", generate_password_hash("1234"), "staff", 1))
        c.execute("INSERT INTO user(name,phone,pin_hash,role) VALUES (?,?,?,?)",
                  ("Admin", "0788000000", generate_password_hash("admin1"), "admin"))
        c.commit()
        c.close()
        self.client = a.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    # helpers
    def token(self, client=None):
        client = client or self.client
        client.get("/login")
        with client.session_transaction() as s:
            return s["csrf"]

    def login(self, phone="0788000001", pin="1234", client=None):
        client = client or self.client
        return client.post("/login", data={"phone": phone, "pin": pin, "csrf": self.token(client)})

    def rows(self, sql, *args):
        c = sqlite3.connect(a.DB_PATH)
        try:
            return c.execute(sql, args).fetchall()
        finally:
            c.close()

    # ---------- public pages ----------
    def test_home_in_both_languages(self):
        for url in ("/", "/?lang=rw", "/?q=paracetamol", "/?q=zzz&lang=rw"):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_empty_search_shows_empty_state(self):
        html = self.client.get("/?q=nosuchmedicine").get_data(as_text=True)
        self.assertIn("No facility has", html)

    def test_search_finds_by_name_brand_strength_and_form(self):
        for q in ("paracetamol", "panadol", "500mg", "paracetamol tablet", "Paracetamol 500mg"):
            html = self.client.get("/?q=" + q).get_data(as_text=True)
            self.assertIn("Near Pharmacy", html, q)

    def test_percent_sign_is_not_a_wildcard(self):
        html = self.client.get("/?q=%25").get_data(as_text=True)
        self.assertNotIn("Near Pharmacy", html)

    def test_facility_type_filter(self):
        html = self.client.get("/?q=paracetamol&type=health_center").get_data(as_text=True)
        self.assertIn("Far Health Center", html)
        self.assertNotIn("Near Pharmacy", html)

    def test_old_stock_is_unverified(self):
        with a.app.app_context():
            results = a.search_stock("amoxicillin")
        self.assertEqual(results[0]["status"], "unverified")

    def test_distance_sort_puts_nearest_first(self):
        with a.app.app_context():
            r = a.search_stock("paracetamol", origin=(-1.9487, 30.1262), sort="distance")
        available = [x["facility"] for x in r if x["status"] != "out"]
        self.assertEqual(available, ["Near Pharmacy", "Far Health Center"])
        self.assertLess(r[0]["distance_km"], 0.1)

    def test_bad_coordinates_are_ignored(self):
        html = self.client.get("/?q=paracetamol&sort=distance&lat=nan&lng=1").get_data(as_text=True)
        self.assertNotIn("km away", html)

    def test_map_tab_only_when_coordinates_exist(self):
        self.assertIn('id="tab-map"', self.client.get("/?q=paracetamol").get_data(as_text=True))
        self.assertIn("1 facilities have no map location", self.client.get("/?q=paracetamol").get_data(as_text=True))

    def test_suggest_endpoint(self):
        self.assertEqual(self.client.get("/api/suggest?q=p").get_json(), [])
        names = [x["name"] for x in self.client.get("/api/suggest?q=panad").get_json()]
        self.assertEqual(names, ["Paracetamol"])

    # ---------- security ----------
    def test_secret_key_is_not_the_old_default(self):
        self.assertNotEqual(a.app.secret_key, "dev-change-me")
        self.assertGreaterEqual(len(a.app.secret_key), 24)

    def test_security_headers_and_cookie_flags(self):
        r = self.client.get("/")
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")
        self.assertTrue(a.app.config["SESSION_COOKIE_HTTPONLY"])
        self.assertEqual(a.app.config["SESSION_COOKIE_SAMESITE"], "Lax")

    def test_login_success_and_wrong_pin(self):
        self.assertEqual(self.login(pin="9999").status_code, 200)         # stays on the login page
        r = self.login()
        self.assertEqual(r.status_code, 302)
        self.assertIn("/dashboard", r.headers["Location"])

    def test_pin_guessing_is_blocked_after_five_failures(self):
        for _ in range(a.LOGIN_MAX_FAILS):
            self.login(pin="0000")
        self.assertEqual(self.login(pin="1234").status_code, 429)         # even the right PIN is refused

    def test_successful_login_clears_failures(self):
        for _ in range(3):
            self.login(pin="0000")
        self.assertEqual(self.login().status_code, 302)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM login_attempt WHERE phone='0788000001'")[0][0], 0)

    def test_logout_needs_post_and_csrf(self):
        self.login()
        self.assertEqual(self.client.get("/logout").status_code, 405)
        self.assertEqual(self.client.post("/logout").status_code, 400)    # no csrf token
        tok = self.token()
        self.assertEqual(self.client.post("/logout", data={"csrf": tok}).status_code, 302)
        self.assertEqual(self.client.get("/dashboard").status_code, 302)  # logged out

    def test_staff_cannot_open_admin_but_admin_can(self):
        self.login()
        self.assertEqual(self.client.get("/admin/facilities").status_code, 403)
        admin = a.app.test_client()
        self.login("0788000000", "admin1", client=admin)
        for url in ("/admin", "/admin/facilities", "/admin/medicines"):
            self.assertEqual(admin.get(url).status_code, 200, url)

    # ---------- stock and feedback ----------
    def test_stock_update_is_saved_and_audited(self):
        self.login()
        tok = self.token()
        r = self.client.post("/dashboard", data={"medicine_id": "1", "quantity": "7", "csrf": tok})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.rows("SELECT quantity FROM stock_record WHERE facility_id=1 AND medicine_id=1")[0][0], 7)
        hist = self.rows("SELECT user_id, quantity FROM stock_history")
        self.assertEqual(hist, [(1, 7)])

    def test_negative_stock_is_rejected(self):
        self.login()
        tok = self.token()
        self.client.post("/dashboard", data={"medicine_id": "1", "quantity": "-5", "csrf": tok})
        self.assertEqual(self.rows("SELECT quantity FROM stock_record WHERE facility_id=1 AND medicine_id=1")[0][0], 100)

    def test_feedback_is_stored_once_per_session(self):
        tok = self.token()
        data = {"facility_id": "1", "medicine_id": "1", "found": "1", "next": "/", "csrf": tok}
        self.client.post("/feedback", data=data)
        self.client.post("/feedback", data=data)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM feedback")[0][0], 1)

    def test_manager_account_can_be_created(self):
        admin = a.app.test_client()
        self.login("0788000000", "admin1", client=admin)
        tok = self.token(admin)
        admin.post("/admin/staff", data={"role": "manager", "s_name": "Boss", "s_phone": "0788111111",
                                         "s_pin": "4321", "csrf": tok})
        self.assertEqual(self.rows("SELECT role FROM user WHERE phone='0788111111'"), [("manager",)])

    def test_send_reminders_works_for_facility_with_no_stock(self):
        runner = a.app.test_cli_runner()
        result = runner.invoke(args=["send-reminders"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertGreaterEqual(self.rows("SELECT COUNT(*) FROM alert WHERE kind='stale'")[0][0], 1)


if __name__ == "__main__":
    unittest.main()