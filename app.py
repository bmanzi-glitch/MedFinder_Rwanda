"""MedFinder Rwanda - starter web app (Flask + SQLite)."""
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import (Flask, Response, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("MEDFINDER_DB", os.path.join(BASE, "medfinder.db"))

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-change-me")

LOW_FRACTION_DEFAULT = 10      # used when no threshold is set
STALE_HOURS = 48               # SRS 5.5: older than 48h => Unverified

STRINGS = {
    "en": {"title": "MedFinder Rwanda", "search": "Search", "medicine": "Medicine",
           "district": "District", "login": "Staff login",
           "notice": "Availability may change. Please confirm with the facility.",
           "in_stock": "In stock", "low": "Low stock", "out": "Out of stock",
           "unverified": "Unverified", "updated": "Last updated"},
    "rw": {"title": "MedFinder Rwanda", "search": "Shakisha", "medicine": "Umuti",
           "district": "Akarere", "login": "Kwinjira (abakozi)",
           "notice": "Ububiko bushobora guhinduka. Banza ubaze ikigo.",
           "in_stock": "Urahari", "low": "Ni muke", "out": "Washize",
           "unverified": "Ntibyemejwe", "updated": "Ivugurura rya nyuma"},
}


# ---------- database helpers ----------
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    with open(os.path.join(BASE, "schema.sql")) as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


KIGALI = timezone(timedelta(hours=2))


@app.template_filter("kigali")
def kigali_filter(iso):
    """Exact time in Rwanda (UTC+2), for tooltips."""
    return datetime.fromisoformat(iso).astimezone(KIGALI).strftime("%d %b %Y, %H:%M")


@app.template_filter("ago")
def ago_filter(iso):
    """Friendly relative time, e.g. '2 h ago'."""
    secs = int((datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds())
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{secs // 60} min ago"
    if secs < 86400:
        return f"{secs // 3600} h ago"
    days = secs // 86400
    return f"{days} day{'s' if days != 1 else ''} ago"


def compute_status(quantity, last_updated, min_qty=None):
    """Return one of: out, low, in_stock, unverified (SRS FR 3.3, 5.5)."""
    age = datetime.now(timezone.utc) - datetime.fromisoformat(last_updated)
    if age > timedelta(hours=STALE_HOURS):
        return "unverified"
    if quantity == 0:
        return "out"
    if quantity < (min_qty if min_qty is not None else LOW_FRACTION_DEFAULT):
        return "low"
    return "in_stock"


def search_stock(query, district=None):
    sql = """
      SELECT f.name AS facility, f.type, f.district, f.sector, m.name AS medicine,
             m.strength, s.quantity, s.last_updated, t.min_quantity
      FROM stock_record s
      JOIN facility f ON f.facility_id = s.facility_id AND f.is_active = 1
      JOIN medicine m ON m.medicine_id = s.medicine_id
      LEFT JOIN alert_threshold t
             ON t.facility_id = s.facility_id AND t.medicine_id = s.medicine_id
      WHERE m.name LIKE ?"""
    args = [f"%{query.strip()}%"]
    if district:
        sql += " AND f.district LIKE ?"
        args.append(f"%{district.strip()}%")
    rows = []
    for r in db().execute(sql, args):
        d = dict(r)
        d["status"] = compute_status(r["quantity"], r["last_updated"], r["min_quantity"])
        rows.append(d)
    # best status first, then most recently updated first
    order = {"in_stock": 0, "low": 1, "unverified": 2, "out": 3}
    rows.sort(key=lambda x: x["last_updated"], reverse=True)   # newest first
    rows.sort(key=lambda x: order[x["status"]])                # then best status (stable sort)
    return rows


def log_search(channel, query, district):
    db().execute(
        "INSERT INTO search_request(channel, query_text, district, received_at) VALUES (?,?,?,?)",
        (channel, query[:100], district, now_iso()))
    db().commit()


# ---------- auth ----------
def login_required(role=None):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                return "Forbidden", 403
            return fn(*a, **kw)
        return wrapper
    return deco


@app.context_processor
def inject_lang():
    lang = request.args.get("lang") or session.get("lang", "en")
    if lang not in STRINGS:
        lang = "en"
    session["lang"] = lang
    return {"t": STRINGS[lang], "lang": lang}


# ---------- web routes ----------
@app.route("/")
def home():
    q = request.args.get("q", "").strip()
    district = request.args.get("district", "").strip()
    results = None
    if q:
        results = search_stock(q, district or None)
        log_search("web", q, district)
    districts = [r[0] for r in db().execute("SELECT DISTINCT district FROM facility ORDER BY 1")]
    return render_template("home.html", q=q, district=district, results=results, districts=districts)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        phone = request.form["phone"].strip()
        pin = request.form["pin"]
        user = db().execute("SELECT * FROM user WHERE phone = ?", (phone,)).fetchone()
        if user and check_password_hash(user["pin_hash"], pin):
            session.update(user_id=user["user_id"], role=user["role"],
                           facility_id=user["facility_id"], name=user["name"])
            return redirect(url_for("dashboard" if user["role"] == "staff" else "admin"))
        flash("Invalid phone number or PIN.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/dashboard", methods=["GET", "POST"])
@login_required("staff")
def dashboard():
    fid = session["facility_id"]
    if request.method == "POST":
        med_id = int(request.form["medicine_id"])
        qty = int(request.form["quantity"])
        if qty < 0:
            flash("Quantity cannot be negative.")
            return redirect(url_for("dashboard"))
        ts = now_iso()
        c = db()
        c.execute("""INSERT INTO stock_record(facility_id, medicine_id, quantity, last_updated)
                     VALUES (?,?,?,?)
                     ON CONFLICT(facility_id, medicine_id)
                     DO UPDATE SET quantity=excluded.quantity, last_updated=excluded.last_updated""",
                  (fid, med_id, qty, ts))
        c.execute("""INSERT INTO stock_history(facility_id, medicine_id, quantity, user_id, updated_at)
                     VALUES (?,?,?,?,?)""", (fid, med_id, qty, session["user_id"], ts))
        thr = c.execute("SELECT min_quantity FROM alert_threshold WHERE facility_id=? AND medicine_id=?",
                        (fid, med_id)).fetchone()
        if thr and qty < thr["min_quantity"]:
            name = c.execute("SELECT name FROM medicine WHERE medicine_id=?", (med_id,)).fetchone()["name"]
            c.execute("""INSERT INTO alert(facility_id, medicine_id, message, sent_at)
                         VALUES (?,?,?,?)""",
                      (fid, med_id, f"Low stock: {name} ({qty} left)", ts))
            # TODO: send via SMS gateway (see send_sms below)
        c.commit()
        flash("Stock updated.")
        return redirect(url_for("dashboard"))

    facility = db().execute("SELECT * FROM facility WHERE facility_id=?", (fid,)).fetchone()
    medicines = db().execute("SELECT * FROM medicine ORDER BY name").fetchall()
    stock = db().execute("""SELECT m.name, m.strength, s.quantity, s.last_updated, t.min_quantity
                            FROM stock_record s JOIN medicine m USING (medicine_id)
                            LEFT JOIN alert_threshold t
                              ON t.facility_id=s.facility_id AND t.medicine_id=s.medicine_id
                            WHERE s.facility_id=? ORDER BY m.name""", (fid,)).fetchall()
    rows = [dict(r, status=compute_status(r["quantity"], r["last_updated"], r["min_quantity"]))
            for r in stock]
    return render_template("dashboard.html", facility=facility, medicines=medicines, stock=rows)


@app.route("/admin")
@login_required("admin")
def admin():
    facilities = db().execute("SELECT * FROM facility ORDER BY district, name").fetchall()
    top_out = db().execute("""SELECT m.name, COUNT(*) AS n FROM stock_record s
                              JOIN medicine m USING (medicine_id)
                              WHERE s.quantity = 0 GROUP BY m.name ORDER BY n DESC LIMIT 10""").fetchall()
    searches = db().execute("""SELECT query_text, COUNT(*) AS n FROM search_request
                               GROUP BY lower(query_text) ORDER BY n DESC LIMIT 10""").fetchall()
    return render_template("admin.html", facilities=facilities, top_out=top_out, searches=searches)


# ---------- SMS / USSD (Africa's Talking-style webhook) ----------
def format_sms(results, limit=3):
    if not results:
        return "Not found nearby. Try another district."
    lines = []
    for r in results[:limit]:
        label = {"in_stock": "In stock", "low": "Low", "out": "Out", "unverified": "Unverified"}[r["status"]]
        lines.append(f"{r['facility']} ({r['district']}): {label}")
    return "\n".join(lines)[:160]


@app.route("/ussd", methods=["POST"])
def ussd():
    """Menu: 1 -> medicine name -> district -> result. `text` is '*'-joined inputs."""
    parts = request.form.get("text", "").split("*") if request.form.get("text") else []
    if len(parts) == 0:
        resp = "CON MedFinder Rwanda\n1. Find a medicine\n2. Kinyarwanda"
    elif parts[0] == "1" and len(parts) == 1:
        resp = "CON Enter medicine name:"
    elif parts[0] == "1" and len(parts) == 2:
        resp = "CON Enter district (e.g. Gasabo):"
    elif parts[0] == "1" and len(parts) >= 3:
        results = search_stock(parts[1], parts[2])
        log_search("ussd", parts[1], parts[2])
        resp = "END " + format_sms(results)
    else:
        resp = "END Invalid choice."
    return Response(resp, mimetype="text/plain")


@app.route("/sms", methods=["POST"])
def sms_inbound():
    """Inbound SMS like 'paracetamol Gasabo' -> reply text."""
    text = request.form.get("text", "").strip().split()
    if len(text) < 2:
        return Response("Send: medicine district (e.g. paracetamol Gasabo)", mimetype="text/plain")
    med, district = text[0], text[-1]
    log_search("sms", med, district)
    return Response(format_sms(search_stock(med, district)), mimetype="text/plain")


def send_sms(phone, message):
    """Placeholder: integrate an aggregator (e.g. Africa's Talking) here."""
    app.logger.info("SMS to %s: %s", phone, message)


if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        init_db()
    app.run(debug=True, use_reloader=False)