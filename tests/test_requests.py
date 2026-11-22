"""Tests for staff account requests: the public form and the administrator's review page.

Run from the project folder:   python -m unittest discover -s tests -v
Uses a throw-away database, so your real medfinder.db is never touched.
"""
import os
import sqlite3
import sys
import tempfile
import unittest

os.environ.setdefault("SECRET_KEY", "test-secret-key-used-only-by-unit-tests-123456")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as a                                          # noqa: E402
from werkzeug.security import check_password_hash, generate_password_hash  # noqa: E402


class StaffRequestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        a.DB_PATH = os.path.join(self.tmp.name, "test.db")
        a.init_db()
        c = sqlite3.connect(a.DB_PATH)
        c.execute("INSERT INTO facility(name,type,district,is_active) VALUES ('Near Pharmacy','pharmacy','Gasabo',1)")
        c.execute("INSERT INTO facility(name,type,district,is_active) VALUES ('Closed Pharmacy','pharmacy','Gasabo',0)")
        c.execute("INSERT INTO user(name,phone,pin_hash,role,facility_id) VALUES (?,?,?,?,?)",
                  ("Staff One", "0788000001", generate_password_hash("1234"), "staff", 1))
        c.execute("INSERT INTO user(name,phone,pin_hash,role) VALUES (?,?,?,?)",
                  ("Admin", "0788000000", generate_password_hash("admin1"), "admin"))
        c.execute("INSERT INTO user(name,phone,pin_hash,role,lang) VALUES (?,?,?,?,?)",
                  ("Member", "0788222222", generate_password_hash("7777"), "user", "en"))
        c.commit()
        c.close()
        self.client = a.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def token(self, client=None, path="/staff-request"):
        client = client or self.client
        client.get(path)
        with client.session_transaction() as s:
            return s["csrf"]

    def rows(self, sql, *args):
        c = sqlite3.connect(a.DB_PATH)
        try:
            return c.execute(sql, args).fetchall()
        finally:
            c.close()

    def login(self, phone, pin, client=None):
        client = client or self.client
        return client.post("/login", data={"phone": phone, "pin": pin, "csrf": self.token(client, "/login")})

    def submit(self, client=None, **over):
        client = client or self.client
        data = {"name": "Aline Uwase", "phone": "0788123456", "job_title": "Pharmacist", "facility_id": "1",
                "facility_name": "", "district": "", "message": "", "csrf": self.token(client)}
        data.update(over)
        return client.post("/staff-request", data=data)

    def admin_client(self):
        c = a.app.test_client()
        self.assertEqual(self.login("0788000000", "admin1", c).status_code, 302)
        return c

    def approve(self, client, rid, **data):
        data.setdefault("csrf", self.token(client, "/admin/requests"))
        return client.post(f"/admin/requests/{rid}/approve", data=data)

    # ---------- the public form ----------
    def test_form_page_opens_in_both_languages(self):
        self.assertEqual(self.client.get("/staff-request").status_code, 200)
        self.assertEqual(self.client.get("/staff-request?lang=rw").status_code, 200)

    def test_listed_facility_request_is_saved_as_pending(self):
        r = self.submit(phone="+250 788 123 456")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.rows("SELECT name, phone, facility_id, status FROM staff_request"),
                         [("Aline Uwase", "0788123456", 1, "pending")])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM user WHERE phone='0788123456'")[0][0], 0)   # no account yet

    def test_unlisted_facility_needs_name_and_district(self):
        self.assertEqual(self.submit(facility_id="0").status_code, 200)
        self.assertEqual(self.submit(facility_id="0", facility_name="New Pharmacy").status_code, 200)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM staff_request")[0][0], 0)
        self.assertEqual(self.submit(facility_id="0", facility_name="New Pharmacy", district="Huye").status_code, 302)
        self.assertEqual(self.rows("SELECT facility_id, facility_name, district FROM staff_request"),
                         [(None, "New Pharmacy", "Huye")])

    def test_bad_input_is_rejected(self):
        for bad in ({"name": "  "}, {"phone": "12345"}, {"facility_id": "2"}, {"facility_id": "999"},
                    {"phone": "0788000001"}, {"phone": "0788000000"}):
            self.assertEqual(self.submit(**bad).status_code, 200, bad)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM staff_request")[0][0], 0)

    def test_second_pending_request_for_same_phone_is_refused(self):
        self.assertEqual(self.submit().status_code, 302)
        self.assertEqual(self.submit().status_code, 200)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM staff_request")[0][0], 1)

    def test_requests_are_limited_per_connection(self):
        c = sqlite3.connect(a.DB_PATH)
        now = a.now_iso()
        c.executemany("INSERT INTO login_attempt(phone, ip, attempted_at) VALUES ('staffreq','127.0.0.1',?)",
                      [(now,)] * a.STAFF_REQUESTS_PER_HOUR)
        c.commit()
        c.close()
        self.assertEqual(self.submit().status_code, 200)
        self.assertEqual(self.rows("SELECT COUNT(*) FROM staff_request")[0][0], 0)

    def test_staff_and_admin_are_sent_away_from_the_form(self):
        self.login("0788000001", "1234")
        self.assertEqual(self.client.get("/staff-request").status_code, 302)

    # ---------- the administrator's page ----------
    def test_only_admin_can_open_review_page(self):
        self.assertEqual(self.client.get("/admin/requests").status_code, 302)          # not logged in
        self.login("0788222222", "7777")
        self.assertEqual(self.client.get("/admin/requests").status_code, 403)          # member
        staff = a.app.test_client()
        self.login("0788000001", "1234", staff)
        self.assertEqual(staff.get("/admin/requests").status_code, 403)                # staff
        self.assertEqual(self.admin_client().get("/admin/requests").status_code, 200)

    def test_admin_sees_pending_request_and_badge(self):
        self.submit(message="Please approve")
        page = self.admin_client().get("/admin/requests").get_data(as_text=True)
        self.assertIn("Aline Uwase", page)
        self.assertIn("Please approve", page)
        self.assertIn('class="badge"', page)

    def test_approve_creates_a_working_staff_account(self):
        self.submit()
        admin = self.admin_client()
        rid = self.rows("SELECT request_id FROM staff_request")[0][0]
        self.assertEqual(self.approve(admin, rid, facility_id="1", pin="4321").status_code, 302)
        self.assertEqual(self.rows("SELECT role, facility_id, job_title FROM user WHERE phone='0788123456'"),
                         [("staff", 1, "Pharmacist")])
        self.assertEqual(self.rows("SELECT status FROM staff_request")[0][0], "approved")
        newcomer = a.app.test_client()
        self.assertEqual(self.login("0788123456", "4321", newcomer).status_code, 302)
        self.assertEqual(newcomer.get("/dashboard").status_code, 200)

    def test_approve_needs_a_valid_pin_and_facility(self):
        self.submit(facility_id="0", facility_name="New Pharmacy", district="Huye")
        admin = self.admin_client()
        rid = self.rows("SELECT request_id FROM staff_request")[0][0]
        self.approve(admin, rid, facility_id="", pin="4321")           # no facility chosen
        self.approve(admin, rid, facility_id="1", pin="12")            # PIN too short
        self.approve(admin, rid, facility_id="2", pin="4321")          # facility is inactive
        self.assertEqual(self.rows("SELECT COUNT(*) FROM user WHERE phone='0788123456'")[0][0], 0)
        self.assertEqual(self.rows("SELECT status FROM staff_request")[0][0], "pending")

    def test_approve_upgrades_an_existing_member_and_keeps_the_pin(self):
        self.submit(phone="0788222222", name="Member")
        admin = self.admin_client()
        rid = self.rows("SELECT request_id FROM staff_request")[0][0]
        self.approve(admin, rid, facility_id="1")                       # no PIN needed
        role, fid, pin_hash = self.rows("SELECT role, facility_id, pin_hash FROM user WHERE phone='0788222222'")[0]
        self.assertEqual((role, fid), ("staff", 1))
        self.assertTrue(check_password_hash(pin_hash, "7777"))
        self.assertEqual(self.rows("SELECT COUNT(*) FROM user WHERE phone='0788222222'")[0][0], 1)

    def test_reject_and_double_handling(self):
        self.submit()
        admin = self.admin_client()
        rid = self.rows("SELECT request_id FROM staff_request")[0][0]
        token = self.token(admin, "/admin/requests")
        self.assertEqual(admin.post(f"/admin/requests/{rid}/reject", data={"csrf": token}).status_code, 302)
        self.assertEqual(self.rows("SELECT status FROM staff_request")[0][0], "rejected")
        self.approve(admin, rid, facility_id="1", pin="4321")           # already handled: nothing happens
        self.assertEqual(self.rows("SELECT COUNT(*) FROM user WHERE phone='0788123456'")[0][0], 0)
        self.assertEqual(self.rows("SELECT status FROM staff_request")[0][0], "rejected")

    def test_a_non_admin_cannot_approve(self):
        self.submit()
        rid = self.rows("SELECT request_id FROM staff_request")[0][0]
        self.login("0788222222", "7777")
        r = self.client.post(f"/admin/requests/{rid}/approve",
                             data={"facility_id": "1", "pin": "4321", "csrf": self.token(self.client, "/settings")})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.rows("SELECT status FROM staff_request")[0][0], "pending")

    def test_home_page_button_leads_to_the_form(self):
        self.assertIn("/staff-request", self.client.get("/").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
