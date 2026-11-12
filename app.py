"""MedFinder Rwanda - Flask + SQLite, English + Kinyarwanda."""
import os
import secrets
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

LOW_FRACTION_DEFAULT = 10      # "low" when no threshold is set
STALE_HOURS = 48               # SRS 5.5: older than 48h => Unverified
REMINDER_HOURS = 24            # SRS FR 5.2: remind staff after 24h without an update
VALID_TYPES = ("pharmacy", "health_center", "hospital")

# ---------------------------------------------------------------------------
# Translations. Every piece of text shown to users lives here, in both languages.
# Have a native Kinyarwanda speaker review the "rw" block before the pilot.
# ---------------------------------------------------------------------------
STRINGS = {
    "en": {
        "title": "MedFinder Rwanda",
        "login": "Staff login", "nav_login": "Staff login", "logout": "Log out",
        "csrf_error": "Your session expired. Go back, refresh the page and try again.",
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
        "in_stock": "In stock", "low": "Low stock", "out": "Out of stock", "unverified": "Unverified",
        "type_pharmacy": "Pharmacy", "type_health_center": "Health center", "type_hospital": "Hospital",
        # login
        "login_lead": "For pharmacy and health center staff. Log in to update your stock.",
        "phone": "Phone number", "pin": "PIN", "login_btn": "Log in",
        "bad_login": "Invalid phone number or PIN.",
        # staff dashboard
        "dash_lead": "Update your stock every day so patients see what is really available.",
        "stat_tracked": "Medicines tracked", "stat_low": "Running low", "stat_out": "Out of stock",
        "update_h": "Update stock", "qty": "Quantity in stock", "qty_ph": "0 means out of stock",
        "save": "Save stock", "current_h": "Current stock",
        "th_medicine": "Medicine", "th_qty": "Quantity", "th_status": "Status", "th_alert": "Alert below",
        "not_set": "Not set",
        "empty_stock": "No stock saved yet. Pick a medicine above and enter how many you have.",
        "stock_saved": "Stock updated.", "neg_qty": "Quantity cannot be negative.",
        "bad_input": "Choose a medicine and enter a whole number.",
        "thr_h": "Low-stock alert", "thr_lead": "You get an SMS when stock falls below this number.",
        "thr_label": "Alert when below", "thr_save": "Save alert level", "thr_saved": "Alert level saved.",
        "alert_msg": "Low stock: {name} ({qty} left)",
        "reminder_msg": "MedFinder: please update your stock today.",
        # admin navigation + overview
        "nav_overview": "Overview", "nav_facilities": "Facilities", "nav_medicines": "Medicines",
        "admin_h": "Admin overview", "stat_facilities": "Active facilities",
        "stat_low_now": "Low or out of stock now", "stat_stale": "Facilities with stock older than 24 h",
        "filter": "Filter",
        "low_monitor_h": "Low and out of stock now", "th_facility": "Facility",
        "no_low": "Nothing is low or out of stock.",
        "stale_h": "Facilities with stock not updated in 24 hours", "never": "Never updated",
        "no_stale": "All stock was updated in the last 24 hours.", "th_last": "Oldest update",
        "top_out_h": "Medicines most often out of stock",
        "facility_one": "facility", "facility_many": "facilities",
        "searches_h": "What people search for",
        "no_out": "No stock-outs recorded.", "no_searches": "No searches yet. Try the home page.",
        # admin facilities
        "fac_add_h": "Register a facility", "f_name": "Facility name", "f_type": "Type",
        "f_sector": "Sector", "f_lat": "Latitude (optional)", "f_lng": "Longitude (optional)",
        "staff_first_h": "First staff account (optional)", "s_name": "Staff name", "s_title": "Job title",
        "s_pin": "PIN (4 to 6 digits)", "add_facility": "Register facility",
        "fac_added": "Facility registered.", "fac_need": "Enter the facility name, district and a valid type.",
        "fac_list_h": "All facilities", "th_name": "Name", "th_type": "Type", "th_district": "District",
        "th_staff": "Staff", "th_action": "Action", "active": "Active", "inactive": "Inactive",
        "toggle_off": "Deactivate", "toggle_on": "Activate", "fac_toggled": "Facility updated.",
        "staff_add_h": "Add an account", "add_staff": "Add staff", "staff_added": "Account created.",
        "staff_invalid": "Enter a name, a phone number and a PIN of 4 to 6 digits.",
        "phone_taken": "That phone number already has an account.",
        # admin medicines
        "med_add_h": "Add a medicine", "m_name": "Medicine name",
        "m_strength": "Strength, e.g. 500mg", "m_form": "Form, e.g. tablet",
        "add_medicine": "Add medicine", "med_added": "Medicine added.", "med_saved": "Medicine updated.",
        "med_need": "Enter the medicine name.", "med_exists": "This medicine, strength and form already exist.",
        "med_list_h": "Medicine catalog", "save_short": "Save",
        # patient feedback + reports
        "fb_ask": "Did you go here?", "fb_yes": "Yes, it was there", "fb_no": "No, it was not",
        "fb_thanks": "Thank you. Your answer helps keep stock information accurate.",
        "reports_h": "Reports", "role_label": "Role", "role_staff": "Facility staff", "role_manager": "Manager",
        "mgr_note": "Managers see reports only and need no facility.",
        "acc_h": "Do patients find the medicine?", "stat_accuracy": "Search accuracy (target 80%)",
        "stat_wasted": "Wasted trips reported", "stat_responses": "Patient answers",
        "no_feedback": "No patient answers yet.", "th_answers": "Answers", "th_found": "Found it",
        "th_accuracy": "Accuracy", "unmet_h": "Searches with no result",
        "no_unmet": "Every search found a facility.", "th_query": "Search", "th_times": "Times",
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
        "csrf_error": "Igihe cyawe cyarangiye. Subira inyuma, ushyire urupapuro ku murongo wongere ugerageze.",
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
        "th_medicine": "Umuti", "th_qty": "Ingano", "th_status": "Uko bimeze", "th_alert": "Integuza munsi ya",
        "not_set": "Ntirwashyizweho",
        "empty_stock": "Nta bubiko bubitswe. Hitamo umuti hejuru wandike ingano ufite.",
        "stock_saved": "Ububiko bwavuguruwe.", "neg_qty": "Ingano ntishobora kuba munsi ya zeru.",
        "bad_input": "Hitamo umuti wandike umubare wuzuye.",
        "thr_h": "Integuza y'ububiko bucye",
        "thr_lead": "Uzohererezwa SMS ububiko nibujya munsi y'uyu mubare.",
        "thr_label": "Mbimenyeshe iyo biri munsi ya", "thr_save": "Bika urugero rw'integuza",
        "thr_saved": "Urugero rw'integuza rwabitswe.",
        "alert_msg": "Umuti {name} uri gushira: hasigaye {qty}",
        "reminder_msg": "MedFinder: vugurura ububiko bwawe uyu munsi.",
        "nav_overview": "Incamake", "nav_facilities": "Ibigo", "nav_medicines": "Imiti",
        "admin_h": "Incamake y'ubuyobozi", "stat_facilities": "Ibigo bikora",
        "stat_low_now": "Imiti iri gushira cyangwa yashize ubu", "stat_stale": "Ibigo bifite ububiko burengeje amasaha 24",
        "filter": "Shungura",
        "low_monitor_h": "Imiti iri gushira cyangwa yashize ubu", "th_facility": "Ikigo",
        "no_low": "Nta muti uri gushira cyangwa washize.",
        "stale_h": "Ibigo bifite ububiko butavuguruwe mu masaha 24", "never": "Ntibigeze bivugurura",
        "no_stale": "Ububiko bwose bwavuguruwe mu masaha 24 ashize.", "th_last": "Ivugurura rya kera cyane",
        "top_out_h": "Imiti ikunze gushira mu bubiko",
        "facility_one": "ikigo", "facility_many": "ibigo",
        "searches_h": "Ibyo abantu bashakisha",
        "no_out": "Nta muti n'umwe washize.", "no_searches": "Nta wari washakisha. Gerageza ku rupapuro rw'itangiriro.",
        "fac_add_h": "Andikisha ikigo", "f_name": "Izina ry'ikigo", "f_type": "Ubwoko",
        "f_sector": "Umurenge", "f_lat": "Latitude (si ngombwa)", "f_lng": "Longitude (si ngombwa)",
        "staff_first_h": "Konti y'umukozi wa mbere (si ngombwa)", "s_name": "Izina ry'umukozi",
        "s_title": "Umwanya", "s_pin": "PIN (imibare 4 kugeza kuri 6)", "add_facility": "Andikisha ikigo",
        "fac_added": "Ikigo cyanditswe.", "fac_need": "Andika izina, akarere n'ubwoko nyabwo bw'ikigo.",
        "fac_list_h": "Ibigo byose", "th_name": "Izina", "th_type": "Ubwoko", "th_district": "Akarere",
        "th_staff": "Abakozi", "th_action": "Igikorwa", "active": "Gikora", "inactive": "Ntigikora",
        "toggle_off": "Hagarika", "toggle_on": "Subiza mu mirimo", "fac_toggled": "Ikigo cyavuguruwe.",
        "staff_add_h": "Ongeramo konti", "add_staff": "Ongeramo umukozi",
        "staff_added": "Konti yaremwe.",
        "staff_invalid": "Andika izina, nimero ya telefone na PIN y'imibare 4 kugeza kuri 6.",
        "phone_taken": "Iyi nimero ya telefone isanzwe ifite konti.",
        "med_add_h": "Ongeramo umuti", "m_name": "Izina ry'umuti",
        "m_strength": "Ingano, urugero: 500mg", "m_form": "Ubwoko, urugero: tablet",
        "add_medicine": "Ongeramo umuti", "med_added": "Umuti wongeweho.", "med_saved": "Umuti wavuguruwe.",
        "med_need": "Andika izina ry'umuti.", "med_exists": "Uyu muti, ingano n'ubwoko byarahari.",
        "med_list_h": "Urutonde rw'imiti", "save_short": "Bika",
        "fb_ask": "Warugeze aha?", "fb_yes": "Yego, nawubonye", "fb_no": "Oya, ntawo nabonye",
        "fb_thanks": "Murakoze. Igisubizo cyawe gifasha kugira amakuru y'ububiko nyayo.",
        "reports_h": "Raporo", "role_label": "Uruhare", "role_staff": "Umukozi w'ikigo", "role_manager": "Umuyobozi",
        "mgr_note": "Abayobozi babona raporo gusa kandi ntibakeneye ikigo.",
        "acc_h": "Abarwayi barawubona?", "stat_accuracy": "Ukuri kw'ibisubizo (intego 80%)",
        "stat_wasted": "Ingendo zapfuye zatanzwe", "stat_responses": "Ibisubizo by'abarwayi",
        "no_feedback": "Nta gisubizo cy'umurwayi kiraboneka.", "th_answers": "Ibisubizo", "th_found": "Barawubonye",
        "th_accuracy": "Ukuri", "unmet_h": "Ishakisha ritabonye ibisubizo",
        "no_unmet": "Buri shakisha ryabonye ikigo.", "th_query": "Ishakisha", "th_times": "Inshuro",
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


# ---------- request hooks ----------
@app.before_request
def pick_language():
    """?lang=rw / ?lang=en switches language and is remembered in the session."""
    lang = request.args.get("lang")
    if lang in STRINGS:
        session["lang"] = lang


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return session["csrf"]


@app.before_request
def csrf_protect():
    """Every browser form POST must carry the session's token. SMS/USSD webhooks are exempt."""
    if request.method == "POST" and request.endpoint not in ("sms_inbound", "ussd"):
        sent = request.form.get("csrf", "")
        if not sent or not secrets.compare_digest(sent, session.get("csrf", "")):
            return Response(tr("csrf_error"), status=400, mimetype="text/plain")


@app.context_processor
def inject_globals():
    def lang_url(code):
        """Current page URL with the language swapped, so a search is kept."""
        args = request.args.to_dict()
        args["lang"] = code
        return url_for(request.endpoint, **args)
    return {"t": STRINGS[current_lang()], "lang": current_lang(),
            "lang_url": lang_url, "csrf_token": csrf_token}


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
      SELECT f.facility_id, m.medicine_id, f.name AS facility, f.type, f.district, f.sector, m.name AS medicine,
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


def log_search(channel, query, district, result_count=None):
    db().execute(
        "INSERT INTO search_request(channel, query_text, district, result_count, received_at) VALUES (?,?,?,?,?)",
        (channel, query[:100], district, result_count, now_iso()))
    db().commit()


# ---------- SMS sending ----------
def send_sms(phone, message):
    """Send one SMS. Returns True if handed to a gateway, False otherwise.
    TODO: integrate an aggregator (e.g. Africa's Talking) here. Until then the message is only logged."""
    app.logger.warning("SMS gateway not configured. To %s: %s", phone, message)
    return False


def facility_phones(c, facility_id):
    return [r["phone"] for r in c.execute(
        "SELECT phone FROM user WHERE facility_id=? AND role='staff'", (facility_id,))]


def raise_low_stock_alert(c, fid, med_id, qty, ts):
    """Save an Alert record and text the facility's staff (SRS FR 5.1)."""
    name = c.execute("SELECT name FROM medicine WHERE medicine_id=?", (med_id,)).fetchone()["name"]
    msg = tr("alert_msg").format(name=name, qty=qty)
    cur = c.execute("INSERT INTO alert(facility_id, medicine_id, kind, message, sent_at) VALUES (?,?,'low',?,?)",
                    (fid, med_id, msg, ts))
    phones = facility_phones(c, fid)
    delivered = bool(phones) and all([send_sms(p, msg) for p in phones])
    c.execute("UPDATE alert SET delivery_status=? WHERE alert_id=?",
              ("sent" if delivered else "pending", cur.lastrowid))


def stale_facilities(hours=REMINDER_HOURS):
    """Active facilities that need a reminder (SRS FR 5.2): at least one medicine's stock has not been
    updated in `hours`, or nothing was ever recorded. `last` is the facility's OLDEST stock update."""
    rows = db().execute("""SELECT f.facility_id, f.name, f.district, MIN(s.last_updated) AS last
                           FROM facility f LEFT JOIN stock_record s ON s.facility_id = f.facility_id
                           WHERE f.is_active = 1 GROUP BY f.facility_id ORDER BY f.district, f.name""").fetchall()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    return [r for r in rows if r["last"] is None or datetime.fromisoformat(r["last"]) < cutoff]


@app.cli.command("send-reminders")
def send_reminders_cmd():
    """Text staff of facilities that have not updated stock in 24 hours (SRS FR 5.2). Run once a day.
    Each reminder is saved as an Alert of kind 'stale'; a facility is not texted twice within 20 hours."""
    msg = STRINGS["en"]["reminder_msg"] + " / " + STRINGS["rw"]["reminder_msg"]
    recent_cutoff = (datetime.now(timezone.utc) - timedelta(hours=20)).isoformat(timespec="seconds")
    c = db()
    stale, texted = stale_facilities(), 0
    for f in stale:
        if c.execute("SELECT 1 FROM alert WHERE facility_id=? AND kind='stale' AND sent_at>?",
                     (f["facility_id"], recent_cutoff)).fetchone():
            continue
        phones = facility_phones(c, f["facility_id"])
        results = [send_sms(p, msg) for p in phones]
        texted += sum(results)
        c.execute("""INSERT INTO alert(facility_id, medicine_id, kind, message, sent_at, delivery_status)
                     VALUES (?,NULL,'stale',?,?,?)""",
                  (f["facility_id"], msg, now_iso(), "sent" if phones and all(results) else "pending"))
    c.commit()
    print(f"{len(stale)} facilities overdue, {texted} SMS handed to the gateway.")


# ---------- auth ----------
def login_required(role=None):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if role and session.get("role") not in ((role,) if isinstance(role, str) else role):
                return "Forbidden", 403
            return fn(*a, **kw)
        return wrapper
    return deco


def create_staff(c, name, phone, pin, facility_id, job_title="", role="staff"):
    """Insert a staff or manager account. Returns None on success, or a STRINGS key naming the problem."""
    name, phone, job_title = name.strip(), phone.strip().replace(" ", ""), job_title.strip()
    if not name or not phone or not (pin.isdigit() and 4 <= len(pin) <= 6):
        return "staff_invalid"
    if c.execute("SELECT 1 FROM user WHERE phone=?", (phone,)).fetchone():
        return "phone_taken"
    c.execute("INSERT INTO user(name,phone,pin_hash,role,job_title,facility_id) VALUES (?,?,?,?,?,?)",
              (name, phone, generate_password_hash(pin), role, job_title or None, facility_id))
    return None


# ---------- public routes ----------
@app.route("/")
def home():
    q = request.args.get("q", "").strip()
    district = request.args.get("district", "").strip()
    results = None
    if q:
        results = search_stock(q, district or None)
        if "lang" not in request.args:          # don't count a language switch as a new search
            log_search("web", q, district, len(results))
    districts = [r[0] for r in db().execute("SELECT DISTINCT district FROM facility ORDER BY 1")]
    return render_template("home.html", q=q, district=district, results=results, districts=districts)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        phone = request.form.get("phone", "").strip().replace(" ", "")
        pin = request.form.get("pin", "")
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


@app.route("/feedback", methods=["POST"])
def feedback():
    """Patient answers 'Was it in stock?'. Used to measure the 80% accuracy and 30% wasted-trip targets.
    Stores no personal data (NFR 11): only facility, medicine, yes/no and the status that was shown."""
    nxt = request.form.get("next", "/")
    if not nxt.startswith("/") or nxt.startswith("//"):
        nxt = "/"
    try:
        fid, mid, found = int(request.form["facility_id"]), int(request.form["medicine_id"]), int(request.form["found"])
    except (KeyError, ValueError):
        found = None
    row = None
    if found in (0, 1):
        row = db().execute("""SELECT s.quantity, s.last_updated, t.min_quantity
                              FROM stock_record s
                              JOIN facility f ON f.facility_id = s.facility_id AND f.is_active = 1
                              LEFT JOIN alert_threshold t
                                     ON t.facility_id = s.facility_id AND t.medicine_id = s.medicine_id
                              WHERE s.facility_id=? AND s.medicine_id=?""", (fid, mid)).fetchone()
    if not row:
        flash(tr("bad_input"))
        return redirect(nxt)
    answered = session.get("fb", [])
    key = f"{fid}-{mid}"
    if key not in answered:                      # one answer per facility+medicine per browser session
        db().execute("""INSERT INTO feedback(facility_id, medicine_id, found, status_shown, created_at)
                        VALUES (?,?,?,?,?)""",
                     (fid, mid, found, compute_status(row["quantity"], row["last_updated"], row["min_quantity"]), now_iso()))
        db().commit()
        session["fb"] = answered + [key]
    flash(tr("fb_thanks"))
    return redirect(nxt)


# ---------- staff ----------
def parse_med_and_qty():
    """Read medicine_id and a number from the form. Returns (med_id, number) or None if invalid."""
    try:
        med_id = int(request.form["medicine_id"])
        number = int(request.form["quantity" if "quantity" in request.form else "min_quantity"])
    except (KeyError, ValueError):
        return None
    if not db().execute("SELECT 1 FROM medicine WHERE medicine_id=?", (med_id,)).fetchone():
        return None
    return med_id, number


@app.route("/dashboard", methods=["GET", "POST"])
@login_required("staff")
def dashboard():
    fid = session["facility_id"]
    if request.method == "POST":
        parsed = parse_med_and_qty()
        if not parsed:
            flash(tr("bad_input"))
            return redirect(url_for("dashboard"))
        med_id, qty = parsed
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
            raise_low_stock_alert(c, fid, med_id, qty, ts)
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


@app.route("/dashboard/threshold", methods=["POST"])
@login_required("staff")
def set_threshold():
    """SRS use case 'Set Alert Threshold': staff choose the level that triggers a low-stock SMS."""
    parsed = parse_med_and_qty()
    if not parsed:
        flash(tr("bad_input"))
    elif parsed[1] < 0:
        flash(tr("neg_qty"))
    else:
        med_id, minq = parsed
        db().execute("""INSERT INTO alert_threshold(facility_id, medicine_id, min_quantity) VALUES (?,?,?)
                        ON CONFLICT(facility_id, medicine_id) DO UPDATE SET min_quantity=excluded.min_quantity""",
                     (session["facility_id"], med_id, minq))
        db().commit()
        flash(tr("thr_saved"))
    return redirect(url_for("dashboard"))


# ---------- admin ----------
@app.route("/admin")
@login_required(("admin", "manager"))
def admin():
    """Reports. Admins and managers can both view them; only admins get the management pages."""
    district = request.args.get("district", "").strip()
    dfilter, dargs = (" AND f.district = ?", [district]) if district else ("", [])

    rows = db().execute(f"""SELECT f.name AS facility, f.district, m.name AS medicine, m.strength,
                                   s.quantity, s.last_updated, t.min_quantity
                            FROM stock_record s
                            JOIN facility f ON f.facility_id = s.facility_id AND f.is_active = 1
                            JOIN medicine m ON m.medicine_id = s.medicine_id
                            LEFT JOIN alert_threshold t
                                   ON t.facility_id = s.facility_id AND t.medicine_id = s.medicine_id
                            WHERE 1=1 {dfilter}""", dargs).fetchall()
    low = []
    for r in rows:
        status = compute_status(r["quantity"], r["last_updated"], r["min_quantity"])
        if status in ("low", "out"):
            low.append(dict(r, status=status))
    low.sort(key=lambda x: ({"out": 0, "low": 1}[x["status"]], x["district"], x["facility"]))

    stale = [r for r in stale_facilities() if not district or r["district"] == district]
    top_out = db().execute(f"""SELECT m.name, COUNT(*) AS n FROM stock_record s
                               JOIN facility f ON f.facility_id = s.facility_id AND f.is_active = 1
                               JOIN medicine m USING (medicine_id)
                               WHERE s.quantity = 0 {dfilter}
                               GROUP BY m.name ORDER BY n DESC LIMIT 10""", dargs).fetchall()
    searches = db().execute(f"""SELECT query_text, COUNT(*) AS n FROM search_request
                                {"WHERE district = ?" if district else ""}
                                GROUP BY lower(query_text) ORDER BY n DESC LIMIT 10""", dargs).fetchall()
    # searches that found nothing = medicines people want that no facility lists
    unmet = db().execute(f"""SELECT lower(query_text) AS q, district, COUNT(*) AS n FROM search_request
                             WHERE result_count = 0 {"AND district = ?" if district else ""}
                             GROUP BY lower(query_text), district ORDER BY n DESC LIMIT 10""", dargs).fetchall()
    # patient answers to "Did you go here? Was it there?" - only counted when the app showed it as available
    fb = db().execute(f"""SELECT f.name, f.district, COUNT(*) AS n, SUM(b.found) AS found
                          FROM feedback b JOIN facility f ON f.facility_id = b.facility_id
                          WHERE b.status_shown IN ('in_stock','low') {dfilter}
                          GROUP BY f.facility_id ORDER BY n DESC""", dargs).fetchall()
    fb_total = sum(r["n"] for r in fb)
    fb_found = sum(r["found"] for r in fb)
    accuracy = round(100 * fb_found / fb_total) if fb_total else None

    districts = [r[0] for r in db().execute("SELECT DISTINCT district FROM facility ORDER BY 1")]
    n_active = db().execute(f"SELECT COUNT(*) FROM facility f WHERE f.is_active=1 {dfilter}", dargs).fetchone()[0]
    return render_template("admin.html", low=low, stale=stale, top_out=top_out, searches=searches,
                           unmet=unmet, fb=fb, fb_total=fb_total, fb_wasted=fb_total - fb_found, accuracy=accuracy,
                           districts=districts, district=district, n_active=n_active)


@app.route("/admin/facilities", methods=["GET", "POST"])
@login_required("admin")
def admin_facilities():
    c = db()
    if request.method == "POST":
        f = request.form
        name, district, ftype = f.get("name", "").strip(), f.get("district", "").strip(), f.get("type")
        if not name or not district or ftype not in VALID_TYPES:
            flash(tr("fac_need"))
            return redirect(url_for("admin_facilities"))

        def number(key):
            try:
                return float(f.get(key, "").strip())
            except ValueError:
                return None

        cur = c.execute("INSERT INTO facility(name,type,district,sector,lat,lng) VALUES (?,?,?,?,?,?)",
                        (name, ftype, district, f.get("sector", "").strip() or None, number("lat"), number("lng")))
        if any(f.get(k, "").strip() for k in ("s_name", "s_phone", "s_pin")):
            err = create_staff(c, f.get("s_name", ""), f.get("s_phone", ""), f.get("s_pin", ""),
                               cur.lastrowid, f.get("s_title", ""))
            if err:
                c.rollback()            # don't keep a facility whose first staff account failed
                flash(tr(err))
                return redirect(url_for("admin_facilities"))
        c.commit()
        flash(tr("fac_added"))
        return redirect(url_for("admin_facilities"))

    facilities = c.execute("""SELECT f.*, (SELECT COUNT(*) FROM user u WHERE u.facility_id = f.facility_id) AS staff_count
                              FROM facility f ORDER BY f.district, f.name""").fetchall()
    return render_template("admin_facilities.html", facilities=facilities, valid_types=VALID_TYPES)


@app.route("/admin/facilities/<int:fid>/toggle", methods=["POST"])
@login_required("admin")
def admin_facility_toggle(fid):
    db().execute("UPDATE facility SET is_active = 1 - is_active WHERE facility_id=?", (fid,))
    db().commit()
    flash(tr("fac_toggled"))
    return redirect(url_for("admin_facilities"))


@app.route("/admin/staff", methods=["POST"])
@login_required("admin")
def admin_staff_add():
    """Create a facility staff account (needs a facility) or a manager account (reports only, no facility)."""
    f = request.form
    role = f.get("role", "staff")
    if role not in ("staff", "manager"):
        role = "staff"
    fid = None
    if role == "staff":
        try:
            fid = int(f.get("facility_id", ""))
        except ValueError:
            fid = None
        if fid is None or not db().execute("SELECT 1 FROM facility WHERE facility_id=?", (fid,)).fetchone():
            flash(tr("fac_need"))
            return redirect(url_for("admin_facilities"))
    err = create_staff(db(), f.get("s_name", ""), f.get("s_phone", ""), f.get("s_pin", ""),
                       fid, f.get("s_title", ""), role)
    if err:
        db().rollback()
        flash(tr(err))
    else:
        db().commit()
        flash(tr("staff_added"))
    return redirect(url_for("admin_facilities"))


@app.route("/admin/medicines", methods=["GET", "POST"])
@login_required("admin")
def admin_medicines():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash(tr("med_need"))
        else:
            try:
                db().execute("INSERT INTO medicine(name,strength,form) VALUES (?,?,?)",
                             (name, request.form.get("strength", "").strip(), request.form.get("form", "").strip()))
                db().commit()
                flash(tr("med_added"))
            except sqlite3.IntegrityError:
                flash(tr("med_exists"))
        return redirect(url_for("admin_medicines"))
    medicines = db().execute("SELECT * FROM medicine ORDER BY name, strength").fetchall()
    return render_template("admin_medicines.html", medicines=medicines)


@app.route("/admin/medicines/<int:mid>/edit", methods=["POST"])
@login_required("admin")
def admin_medicine_edit(mid):
    name = request.form.get("name", "").strip()
    if not name:
        flash(tr("med_need"))
    else:
        try:
            db().execute("UPDATE medicine SET name=?, strength=?, form=? WHERE medicine_id=?",
                         (name, request.form.get("strength", "").strip(), request.form.get("form", "").strip(), mid))
            db().commit()
            flash(tr("med_saved"))
        except sqlite3.IntegrityError:
            flash(tr("med_exists"))
    return redirect(url_for("admin_medicines"))


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
                log_search("ussd", parts[1], parts[2], len(results))
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
    log_search("sms", " ".join(med_words), district, len(results))
    return Response(format_sms(results, lang), mimetype="text/plain")


if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        init_db()
    app.run(debug=True, use_reloader=False)