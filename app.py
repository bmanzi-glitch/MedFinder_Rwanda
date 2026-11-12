"""MedFinder Rwanda - starter web app (Flask + SQLite), English + Kinyarwanda."""
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import (Flask, Response, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("MEDFINDER_DB", os.path.join(BASE, "medfinder.db"))

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-change-me")

LOW_FRACTION_DEFAULT = 10      # used when no threshold is set
STALE_HOURS = 48               # SRS 5.5: older than 48h => Unverified

# ---------------------------------------------------------------------------
# Translations. Every piece of text shown to users lives here, in both languages.
# Have a native Kinyarwanda speaker review the "rw" block before the pilot.
# ---------------------------------------------------------------------------
STRINGS = {
    "en": {
        "title": "MedFinder Rwanda",
        # header
        "login": "Staff login", "nav_login": "Staff login", "logout": "Log out",
        # home
        "hero_title": "Find your medicine before you travel",
        "hero_lead": "See which pharmacies and health centers have it in stock, so you don't make a trip for nothing.",
        "search": "Search", "medicine": "Medicine", "medicine_ph": "Medicine, e.g. Paracetamol",
        "district": "District", "district_all": "All districts",
        "common": "Common searches",
        "result_one": "result for", "result_many": "results for", "in_word": "in",
        "empty_pre": "No facility has", "empty_post": "yet",
        "empty_hint": "Check the spelling, or try a different district. Facilities update their stock every day.",
        "search_all": "Search all districts",
        "notice": "Availability may change. Please confirm with the facility.",
        "updated": "Last updated",
        # statuses
        "in_stock": "In stock", "low": "Low stock", "out": "Out of stock", "unverified": "Unverified",
        # facility types
        "type_pharmacy": "Pharmacy", "type_health_center": "Health center", "type_hospital": "Hospital",
        # login
        "login_lead": "For pharmacy and health center staff. Log in to update your stock.",
        "phone": "Phone number", "pin": "PIN", "login_btn": "Log in",
        "bad_login": "Invalid phone number or PIN.",
        # dashboard
        "dash_lead": "Update your stock every day so patients see what is really available.",
        "stat_tracked": "Medicines tracked", "stat_low": "Running low", "stat_out": "Out of stock",
        "update_h": "Update stock", "qty": "Quantity in stock", "qty_ph": "0 means out of stock",
        "save": "Save stock", "current_h": "Current stock",
        "th_medicine": "Medicine", "th_qty": "Quantity", "th_status": "Status",
        "empty_stock": "No stock saved yet. Pick a medicine above and enter how many you have.",
        "stock_saved": "Stock updated.", "neg_qty": "Quantity cannot be negative.",
        "bad_input": "Choose a medicine and enter a whole number.",
        # admin
        "admin_h": "Admin overview", "stat_facilities": "Facilities",
        "stat_meds_out": "Medicines out somewhere", "stat_searches": "Searches (top 10 terms)",
        "facilities_h": "Facilities", "th_name": "Name", "th_type": "Type", "th_district": "District",
        "active": "Active", "inactive": "Inactive",
        "top_out_h": "Medicines most often out of stock",
        "facility_one": "facility", "facility_many": "facilities",
        "searches_h": "What people search for",
        "no_out": "No stock-outs recorded.", "no_searches": "No searches yet. Try the home page.",
        # relative time
        "just_now": "just now", "min_ago": "{n} min ago", "h_ago": "{n} h ago",
        "day_ago": "{n} day ago", "days_ago": "{n} days ago",
        # SMS / USSD
        "ussd_med": "Enter medicine name:", "ussd_district": "Enter district (e.g. Gasabo):",
        "sms_not_found": "Not found nearby. Try another district.",
        "sms_help": "Send: medicine district (e.g. paracetamol Gasabo)",
        "sms_in": "In stock", "sms_low": "Low", "sms_out": "Out", "sms_unv": "Unverified",
    },
    "rw": {
        "title": "MedFinder Rwanda",
        "login": "Kwinjira (abakozi)", "nav_login": "Kwinjira", "logout": "Sohoka",
        "hero_title": "Menya aho umuti uboneka mbere yo gukora urugendo",
        "hero_lead": "Reba farumasi n'ibigo nderabuzima bifite umuti ushaka, kugira ngo utazapfusha ubusa urugendo.",
        "search": "Shakisha", "medicine": "Umuti", "medicine_ph": "Umuti, urugero: Paracetamol",
        "district": "Akarere", "district_all": "Uturere twose",
        "common": "Ibikunze gushakishwa",
        "result_one": "cyabonetse kuri", "result_many": "byabonetse kuri", "in_word": "i",
        "empty_pre": "Nta kigo gifite", "empty_post": "kugeza ubu",
        "empty_hint": "Reba uko wanditse, cyangwa ugerageze akandi karere. Ibigo bivugurura ububiko buri munsi.",
        "search_all": "Shakisha mu turere twose",
        "notice": "Ububiko bushobora guhinduka. Banza ubaze ikigo.",
        "updated": "Ivugurura rya nyuma",
        "in_stock": "Urahari", "low": "Ni muke", "out": "Washize", "unverified": "Ntibyemejwe",
        "type_pharmacy": "Farumasi", "type_health_center": "Ikigo nderabuzima", "type_hospital": "Ibitaro",
        "login_lead": "Ku bakozi ba farumasi n'ibigo nderabuzima. Injira kugira ngo uvugurure ububiko.",
        "phone": "Nimero ya telefone", "pin": "PIN (umubare w'ibanga)", "login_btn": "Injira",
        "bad_login": "Nimero ya telefone cyangwa PIN si byo.",
        "dash_lead": "Vugurura ububiko buri munsi kugira ngo abarwayi babone ibiboneka by'ukuri.",
        "stat_tracked": "Imiti ikurikiranwa", "stat_low": "Iri gushira", "stat_out": "Yashize",
        "update_h": "Vugurura ububiko", "qty": "Ingano mu bubiko", "qty_ph": "0 bisobanura ko yashize",
        "save": "Bika", "current_h": "Ububiko buriho",
        "th_medicine": "Umuti", "th_qty": "Ingano", "th_status": "Uko bimeze",
        "empty_stock": "Nta bubiko bubitswe. Hitamo umuti hejuru wandike ingano ufite.",
        "stock_saved": "Ububiko bwavuguruwe.", "neg_qty": "Ingano ntishobora kuba munsi ya zeru.",
        "bad_input": "Hitamo umuti wandike umubare wuzuye.",
        "admin_h": "Incamake y'ubuyobozi", "stat_facilities": "Ibigo",
        "stat_meds_out": "Imiti yashize ahantu", "stat_searches": "Ishakisha (amagambo 10 ya mbere)",
        "facilities_h": "Ibigo", "th_name": "Izina", "th_type": "Ubwoko", "th_district": "Akarere",
        "active": "Gikora", "inactive": "Ntigikora",
        "top_out_h": "Imiti ikunze gushira mu bubiko",
        "facility_one": "ikigo", "facility_many": "ibigo",
        "searches_h": "Ibyo abantu bashakisha",
        "no_out": "Nta muti n'umwe washize.", "no_searches": "Nta wari washakisha. Gerageza ku rupapuro rw'itangiriro.",
        "just_now": "ubu nyine", "min_ago": "iminota {n} ishize", "h_ago": "amasaha {n} ashize",
        "day_ago": "umunsi {n} ushize", "days_ago": "iminsi {n} ishize",
        "ussd_med": "Andika izina ry'umuti:", "ussd_district": "Andika akarere (urugero: Gasabo):",
        "sms_not_found": "Nta kibonetse. Gerageza akandi karere.",
        "sms_help": "Ohereza: umuti akarere (urugero: paracetamol Gasabo)",
        "sms_in": "Urahari", "sms_low": "Ni muke", "sms_out": "Washize", "sms_unv": "Ntibyemejwe",
    },
}
DEFAULT_LANG = "en"


def current_lang():
    lang = session.get("lang", DEFAULT_LANG)
    return lang if lang in STRINGS else DEFAULT_LANG


def tr(key):
    return STRINGS[current_lang()][key]


@app.before_request
def pick_language():
    """?lang=rw / ?lang=en switches language and is remembered in the session."""
    lang = request.args.get("lang")
    if lang in STRINGS:
        session["lang"] = lang


@app.context_processor
def inject_lang():
    def lang_url(code):
        """Current page URL with the language swapped, so a search is kept."""
        args = request.args.to_dict()
        args["lang"] = code
        return url_for(request.endpoint, **args)
    return {"t": STRINGS[current_lang()], "lang": current_lang(), "lang_url": lang_url}


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
    """Exact Rwanda time (UTC+2), numeric so it reads the same in both languages."""
    return datetime.fromisoformat(iso).astimezone(KIGALI).strftime("%d/%m/%Y %H:%M")


@app.template_filter("ago")
def ago_filter(iso):
    """Relative time in the current language, e.g. '2 h ago' / 'amasaha 2 ashize'."""
    S = STRINGS[current_lang()]
    secs = int((datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds())
    if secs < 60:
        return S["just_now"]
    if secs < 3600:
        return S["min_ago"].format(n=secs // 60)
    if secs < 86400:
        return S["h_ago"].format(n=secs // 3600)
    days = secs // 86400
    return S["day_ago" if days == 1 else "days_ago"].format(n=days)


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


# ---------- web routes ----------
@app.route("/")
def home():
    q = request.args.get("q", "").strip()
    district = request.args.get("district", "").strip()
    results = None
    if q:
        results = search_stock(q, district or None)
        if "lang" not in request.args:          # don't count a language switch as a new search
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
        flash(tr("bad_login"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    lang = current_lang()
    session.clear()
    session["lang"] = lang          # keep the chosen language after logging out
    return redirect(url_for("home"))


@app.route("/dashboard", methods=["GET", "POST"])
@login_required("staff")
def dashboard():
    fid = session["facility_id"]
    if request.method == "POST":
        try:
            med_id = int(request.form["medicine_id"])
            qty = int(request.form["quantity"])
        except (KeyError, ValueError):
            flash(tr("bad_input"))
            return redirect(url_for("dashboard"))
        if qty < 0:
            flash(tr("neg_qty"))
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
        flash(tr("stock_saved"))
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


# ---------- SMS / USSD (Africa's Talking-style webhooks) ----------
def format_sms(results, lang="en", limit=3):
    S = STRINGS[lang]
    if not results:
        return S["sms_not_found"]
    label = {"in_stock": S["sms_in"], "low": S["sms_low"], "out": S["sms_out"], "unverified": S["sms_unv"]}
    lines = [f"{r['facility']} ({r['district']}): {label[r['status']]}" for r in results[:limit]]
    return "\n".join(lines)[:160]


@app.route("/ussd", methods=["POST"])
def ussd():
    """First screen picks the language (1 English, 2 Kinyarwanda), then:
    medicine name -> district -> result. `text` is the '*'-joined inputs."""
    text = request.form.get("text", "")
    parts = text.split("*") if text else []
    if not parts:
        resp = "CON MedFinder Rwanda\n1. English\n2. Kinyarwanda"
    else:
        lang = {"1": "en", "2": "rw"}.get(parts[0])
        if not lang:
            resp = "END Invalid choice. / Amahitamo si yo."
        else:
            S = STRINGS[lang]
            if len(parts) == 1:
                resp = "CON " + S["ussd_med"]
            elif len(parts) == 2:
                resp = "CON " + S["ussd_district"]
            else:
                results = search_stock(parts[1], parts[2])
                log_search("ussd", parts[1], parts[2])
                resp = "END " + format_sms(results, lang)
    return Response(resp, mimetype="text/plain")


@app.route("/sms", methods=["POST"])
def sms_inbound():
    """Inbound SMS: '[rw|en] medicine district', e.g. 'paracetamol Gasabo' or 'rw amoxicillin 250mg Gasabo'.
    The last word is the district, everything before it is the medicine. Replies in the chosen language."""
    tokens = request.form.get("text", "").strip().split()
    lang = "en"
    if tokens and tokens[0].lower() in ("rw", "en"):
        lang = tokens[0].lower()
        tokens = tokens[1:]
    if len(tokens) < 2:
        return Response(STRINGS[lang]["sms_help"], mimetype="text/plain")
    med_words, district = tokens[:-1], tokens[-1]
    # "amoxicillin 250mg" -> try the full text first, then drop words from the end until something matches
    results = []
    for n in range(len(med_words), 0, -1):
        results = search_stock(" ".join(med_words[:n]), district)
        if results:
            break
    log_search("sms", " ".join(med_words), district)
    return Response(format_sms(results, lang), mimetype="text/plain")


def send_sms(phone, message):
    """Placeholder: integrate an aggregator (e.g. Africa's Talking) here."""
    app.logger.info("SMS to %s: %s", phone, message)


if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        init_db()
    app.run(debug=True, use_reloader=False)