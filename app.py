"""MedFinder Rwanda - Flask + SQLite, English + Kinyarwanda."""
import math
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlencode

from flask import (Flask, Response, abort, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

import migrate
from pages import PAGES
from strings import build_strings

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("MEDFINDER_DB", os.path.join(BASE, "medfinder.db"))
PRODUCTION = os.environ.get("MEDFINDER_ENV") == "production"


def load_secret_key():
    """A real secret is always required. In production it must come from the SECRET_KEY environment
    variable. On a developer machine a random key is created once and kept in .secret_key (not in git)."""
    key = os.environ.get("SECRET_KEY", "").strip()
    if key:
        if len(key) < 24:
            raise RuntimeError("SECRET_KEY is too short. Use at least 24 random characters.")
        return key
    if PRODUCTION:
        raise RuntimeError("Set the SECRET_KEY environment variable before starting MedFinder in production.")
    path = os.path.join(BASE, ".secret_key")
    if os.path.exists(path):
        with open(path) as f:
            saved = f.read().strip()
        if saved:
            return saved
    key = secrets.token_hex(32)
    with open(path, "w") as f:
        f.write(key)
    return key


app = Flask(__name__)
app.secret_key = load_secret_key()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=PRODUCTION,            # cookies only over HTTPS in production
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
)
if os.environ.get("MEDFINDER_BEHIND_PROXY") == "1":     # set when running behind nginx or a load balancer
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# ---------------------------------------------------------------------------
# Stock freshness policy (one place, used everywhere):
#   REMINDER_HOURS - staff get an SMS reminder, and admins see the facility as overdue
#   STALE_HOURS    - patients see "Unverified" instead of a stock status
# ---------------------------------------------------------------------------
LOW_FRACTION_DEFAULT = 10      # "low" when no threshold is set
REMINDER_HOURS = 24            # SRS FR 5.2
STALE_HOURS = 48               # SRS 5.5
VALID_TYPES = ("pharmacy", "health_center", "hospital")
SORTS = ("best", "recent", "distance")

# Optional contact details shown in the footer and on /contact. Nothing is shown until you set them.
CONTACT = {"email": os.environ.get("MEDFINDER_CONTACT_EMAIL", "").strip(),
           "phone": os.environ.get("MEDFINDER_CONTACT_PHONE", "").strip(),
           "address": os.environ.get("MEDFINDER_CONTACT_ADDRESS", "").strip()}
RW_MOBILE = re.compile(r"^07[2389]\d{7}$")     # 072, 073, 078 or 079 followed by 7 digits
SIGNUPS_PER_HOUR = 10                          # per network address
PAGE_SIZE = 30                                 # facilities per page in the directory

# Slowing down PIN guessing
LOGIN_MAX_FAILS = 5            # failed tries per phone number ...
LOGIN_IP_MAX_FAILS = 25        # ... and per network address ...
LOGIN_WINDOW_MIN = 15          # ... within this many minutes
DUMMY_HASH = generate_password_hash("not-a-real-pin")   # keeps timing the same for unknown phone numbers

STRINGS = build_strings(REMINDER_HOURS)      # all text shown to users lives in strings.py

DEFAULT_LANG = "en"


def current_lang():
    lang = session.get("lang", DEFAULT_LANG)
    return lang if lang in STRINGS else DEFAULT_LANG


def tr(key):
    return STRINGS[current_lang()][key]


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
    """Create the database if it is missing, and add any new tables or columns to an older one."""
    conn = sqlite3.connect(DB_PATH)
    migrate.add_missing(conn)
    conn.close()


_prepared_for = None


def prepare_db():
    global _prepared_for
    if _prepared_for != DB_PATH:
        init_db()
        _prepared_for = DB_PATH


# ---------- request hooks ----------
@app.before_request
def ensure_db():
    prepare_db()


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


@app.after_request
def security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Permissions-Policy", "geolocation=(self), camera=(), microphone=()")
    if PRODUCTION:
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return resp


@app.context_processor
def inject_globals():
    def lang_url(code):
        """Current page URL with the language swapped, so a search is kept."""
        args = request.args.to_dict()
        args["lang"] = code
        return request.path + "?" + urlencode(args)       # works for every page, including /facility/3 and 404
    return {"t": STRINGS[current_lang()], "lang": current_lang(),
            "lang_url": lang_url, "csrf_token": csrf_token,
            "contact": CONTACT, "contact_ready": any(CONTACT.values()),
            "year": datetime.now(timezone.utc).year}


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


# ---------- search ----------
def like_pattern(text):
    """'%text%' for LIKE ... ESCAPE '\\', so a typed % or _ is matched literally."""
    esc = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{esc}%"


def haversine_km(lat1, lng1, lat2, lng2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


STATUS_ORDER = {"in_stock": 0, "low": 1, "unverified": 2, "out": 3}


def search_stock(query, district=None, ftype=None, origin=None, sort="best"):
    """Find stock for a medicine. Every word typed must match the medicine's name, strength, form or
    other names (brands), so 'paracetamol 500mg' and 'panadol' both work.
    origin is (lat, lng) of the person, used for the distance and for sort='distance'."""
    sql = """
      SELECT f.facility_id, m.medicine_id, f.name AS facility, f.type, f.district, f.sector, f.lat, f.lng,
             m.name AS medicine, m.strength, m.form, s.quantity, s.last_updated, t.min_quantity
      FROM stock_record s
      JOIN facility f ON f.facility_id = s.facility_id AND f.is_active = 1
      JOIN medicine m ON m.medicine_id = s.medicine_id
      LEFT JOIN alert_threshold t
             ON t.facility_id = s.facility_id AND t.medicine_id = s.medicine_id
      WHERE 1 = 1"""
    args = []
    for word in query.split()[:6]:
        p = like_pattern(word)
        sql += (" AND (m.name LIKE ? ESCAPE '\\' OR m.strength LIKE ? ESCAPE '\\'"
                " OR m.form LIKE ? ESCAPE '\\' OR m.aliases LIKE ? ESCAPE '\\')")
        args += [p, p, p, p]
    if district:
        sql += " AND f.district LIKE ? ESCAPE '\\'"
        args.append(like_pattern(district.strip()))
    if ftype in VALID_TYPES:
        sql += " AND f.type = ?"
        args.append(ftype)
    rows = []
    for r in db().execute(sql, args):
        d = dict(r)
        d["status"] = compute_status(r["quantity"], r["last_updated"], r["min_quantity"])
        d["distance_km"] = (haversine_km(origin[0], origin[1], r["lat"], r["lng"])
                            if origin and r["lat"] is not None and r["lng"] is not None else None)
        rows.append(d)
    if sort == "recent":
        rows.sort(key=lambda x: x["last_updated"], reverse=True)
    elif sort == "distance" and origin:
        # available medicines first, nearest first inside each group
        rows.sort(key=lambda x: (STATUS_ORDER[x["status"]],
                                 x["distance_km"] if x["distance_km"] is not None else 1e9))
    else:
        rows.sort(key=lambda x: x["last_updated"], reverse=True)   # newest first
        rows.sort(key=lambda x: STATUS_ORDER[x["status"]])         # then best status (stable sort)
    return rows


def parse_origin():
    """The person's position from ?lat=&lng=, or None if missing or not a real coordinate."""
    try:
        lat, lng = float(request.args["lat"]), float(request.args["lng"])
    except (KeyError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):      # also rejects nan and inf
        return None
    return round(lat, 4), round(lng, 4)


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
    prepare_db()
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


def normalize_phone(raw):
    """'+250 788 123 456', '250788123456' and '0788 123 456' all become '0788123456'."""
    p = re.sub(r"[\s\-().]", "", raw or "")
    if p.startswith("+250"):
        p = "0" + p[4:]
    elif p.startswith("250") and len(p) == 12:
        p = "0" + p[3:]
    return p


def create_staff(c, name, phone, pin, facility_id, job_title="", role="staff"):
    """Insert a staff or manager account. Returns None on success, or a STRINGS key naming the problem."""
    name, phone, job_title = name.strip(), normalize_phone(phone), job_title.strip()
    if not name or not phone or not (pin.isdigit() and 4 <= len(pin) <= 6):
        return "staff_invalid"
    if c.execute("SELECT 1 FROM user WHERE phone=?", (phone,)).fetchone():
        return "phone_taken"
    c.execute("INSERT INTO user(name,phone,pin_hash,role,job_title,facility_id) VALUES (?,?,?,?,?,?)",
              (name, phone, generate_password_hash(pin), role, job_title or None, facility_id))
    return None


def login_locked(c, phone, ip):
    """True when this phone number or network address has failed too often in the last few minutes."""
    since = (datetime.now(timezone.utc) - timedelta(minutes=LOGIN_WINDOW_MIN)).isoformat(timespec="seconds")
    by_phone = c.execute("SELECT COUNT(*) FROM login_attempt WHERE phone=? AND attempted_at>?",
                         (phone, since)).fetchone()[0]
    by_ip = c.execute("SELECT COUNT(*) FROM login_attempt WHERE ip=? AND attempted_at>?",
                      (ip, since)).fetchone()[0]
    return by_phone >= LOGIN_MAX_FAILS or by_ip >= LOGIN_IP_MAX_FAILS


# ---------- public routes ----------
@app.route("/")
def home():
    q = request.args.get("q", "").strip()
    district = request.args.get("district", "").strip()
    ftype = request.args.get("type", "")
    if ftype not in VALID_TYPES:
        ftype = ""
    sort = request.args.get("sort", "best")
    if sort not in SORTS:
        sort = "best"
    origin = parse_origin()
    if sort == "distance" and not origin:
        sort = "best"

    results, map_points, map_missing, stats = None, [], 0, None
    if q:
        results = search_stock(q, district or None, ftype or None, origin, sort)
        if "lang" not in request.args:          # don't count a language switch as a new search
            log_search("web", q, district, len(results))
        S = STRINGS[current_lang()]
        for r in results:
            if r["lat"] is None or r["lng"] is None:
                map_missing += 1
                continue
            map_points.append({"lat": r["lat"], "lng": r["lng"], "name": r["facility"],
                               "status": r["status"], "label": S[r["status"]],
                               "med": f"{r['medicine']} {r['strength'] or ''}".strip()})
    else:
        row = db().execute("""SELECT COUNT(DISTINCT s.facility_id) AS facilities,
                                     COUNT(DISTINCT s.medicine_id) AS medicines,
                                     MAX(s.last_updated) AS latest
                              FROM stock_record s
                              JOIN facility f ON f.facility_id = s.facility_id AND f.is_active = 1""").fetchone()
        if row["facilities"]:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=REMINDER_HOURS)).isoformat(timespec="seconds")
            fresh = db().execute("""SELECT COUNT(DISTINCT s.facility_id)
                                    FROM stock_record s
                                    JOIN facility f ON f.facility_id = s.facility_id AND f.is_active = 1
                                    WHERE s.last_updated > ?""", (cutoff,)).fetchone()[0]
            stats = dict(row, fresh=fresh)

    districts = [r[0] for r in db().execute("SELECT DISTINCT district FROM facility ORDER BY 1")]
    return render_template("home.html", q=q, district=district, ftype=ftype, sort=sort,
                           lat=origin[0] if origin else "", lng=origin[1] if origin else "",
                           results=results, districts=districts, valid_types=VALID_TYPES,
                           map_points=map_points, map_missing=map_missing, stats=stats,
                           stale_hours=STALE_HOURS, reminder_hours=REMINDER_HOURS)


@app.route("/api/suggest")
def suggest():
    """Autocomplete for the search box: medicines that some active facility actually lists."""
    q = request.args.get("q", "").strip()[:40]
    if len(q) < 2:
        return jsonify([])
    p = like_pattern(q)
    rows = db().execute("""SELECT m.name,
                                  GROUP_CONCAT(DISTINCT trim(coalesce(m.strength,'') || ' ' || coalesce(m.form,''))) AS detail,
                                  MAX(m.aliases) AS aliases
                           FROM medicine m
                           JOIN stock_record s ON s.medicine_id = m.medicine_id
                           JOIN facility f ON f.facility_id = s.facility_id AND f.is_active = 1
                           WHERE m.name LIKE ? ESCAPE '\\' OR m.aliases LIKE ? ESCAPE '\\'
                           GROUP BY m.name ORDER BY m.name LIMIT 8""", (p, p)).fetchall()
    out = []
    for r in rows:
        label = r["name"] + (f" ({r['detail']})" if r["detail"] else "")
        if r["aliases"]:
            label += f" - {r['aliases']}"
        out.append({"name": r["name"], "label": label})
    return jsonify(out)


def record_failure(c, phone, ip):
    c.execute("INSERT INTO login_attempt(phone, ip, attempted_at) VALUES (?,?,?)", (phone[:40], ip, now_iso()))
    c.execute("DELETE FROM login_attempt WHERE attempted_at < ?",
              ((datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds"),))
    c.commit()


def start_session(user):
    """Sign a user in with a fresh session, in their saved language."""
    lang = user["lang"] if user["lang"] in STRINGS else current_lang()
    session.clear()
    session.update(lang=lang, user_id=user["user_id"], role=user["role"],
                   facility_id=user["facility_id"], name=user["name"])
    session.permanent = True                     # expires after 12 hours


def home_for(role):
    return url_for({"staff": "dashboard", "admin": "admin", "manager": "admin"}.get(role, "home"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        phone = normalize_phone(request.form.get("phone", ""))
        pin = request.form.get("pin", "")
        ip = request.remote_addr or "unknown"
        c = db()
        if login_locked(c, phone, ip):
            flash(tr("too_many").format(m=LOGIN_WINDOW_MIN))
            return render_template("login.html"), 429
        user = c.execute("SELECT * FROM user WHERE phone = ?", (phone,)).fetchone()
        if user:
            ok = check_password_hash(user["pin_hash"], pin)
        else:
            check_password_hash(DUMMY_HASH, pin)        # same work whether or not the phone number exists
            ok = False
        if ok:
            c.execute("DELETE FROM login_attempt WHERE phone=?", (phone,))
            c.commit()
            start_session(user)
            return redirect(home_for(user["role"]))
        record_failure(c, phone, ip)
        flash(tr("bad_login"))
    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    """Anyone can create a free member account. Staff and admin accounts are made by an administrator."""
    if "user_id" in session:
        return redirect(url_for("home"))
    form = {"name": "", "phone": ""}
    if request.method == "POST":
        c = db()
        ip = request.remote_addr or "unknown"
        name = request.form.get("name", "").strip()[:60]
        raw_phone = request.form.get("phone", "")
        phone = normalize_phone(raw_phone)
        pin, pin2 = request.form.get("pin", ""), request.form.get("pin2", "")
        form = {"name": name, "phone": raw_phone[:20]}
        hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(timespec="seconds")
        recent = c.execute("SELECT COUNT(*) FROM login_attempt WHERE phone='signup' AND ip=? AND attempted_at>?",
                           (ip, hour_ago)).fetchone()[0]
        error = None
        if recent >= SIGNUPS_PER_HOUR:
            error = "signup_limit"
        elif not name:
            error = "signup_need_name"
        elif not RW_MOBILE.match(phone):
            error = "signup_bad_phone"
        elif not (pin.isdigit() and 4 <= len(pin) <= 6):
            error = "pin_rule"
        elif pin != pin2:
            error = "pin_mismatch"
        elif not request.form.get("agree"):
            error = "agree_needed"
        elif c.execute("SELECT 1 FROM user WHERE phone=?", (phone,)).fetchone():
            error = "phone_taken"
        if error:
            flash(tr(error))
            return render_template("signup.html", form=form)
        c.execute("INSERT INTO user(name,phone,pin_hash,role,lang) VALUES (?,?,?,?,?)",
                  (name, phone, generate_password_hash(pin), "user", current_lang()))
        c.execute("INSERT INTO login_attempt(phone, ip, attempted_at) VALUES ('signup',?,?)", (ip, now_iso()))
        c.commit()
        start_session(c.execute("SELECT * FROM user WHERE phone=?", (phone,)).fetchone())
        flash(tr("welcome").format(name=name))
        return redirect(url_for("home"))
    return render_template("signup.html", form=form)


@app.route("/settings", methods=["GET", "POST"])
@login_required()
def settings():
    """Everyone who is signed in can change their name, language and PIN. Members can also delete their account."""
    c = db()
    ip = request.remote_addr or "unknown"
    user = c.execute("SELECT * FROM user WHERE user_id=?", (session["user_id"],)).fetchone()
    if user is None:                                 # account was removed
        session.clear()
        return redirect(url_for("login"))
    if request.method == "POST":
        action = request.form.get("action")
        if action == "profile":
            name = request.form.get("name", "").strip()[:60]
            lang = request.form.get("lang")
            if not name:
                flash(tr("signup_need_name"))
            else:
                lang = lang if lang in STRINGS else current_lang()
                c.execute("UPDATE user SET name=?, lang=? WHERE user_id=?", (name, lang, user["user_id"]))
                c.commit()
                session["name"], session["lang"] = name, lang
                flash(STRINGS[lang]["set_saved"])
        elif action in ("pin", "delete"):
            if login_locked(c, user["phone"], ip):
                flash(tr("too_many").format(m=LOGIN_WINDOW_MIN))
            elif not check_password_hash(user["pin_hash"], request.form.get("current", "")):
                record_failure(c, user["phone"], ip)
                flash(tr("pin_wrong"))
            elif action == "pin":
                new, new2 = request.form.get("new", ""), request.form.get("new2", "")
                if not (new.isdigit() and 4 <= len(new) <= 6):
                    flash(tr("pin_rule"))
                elif new != new2:
                    flash(tr("pin_mismatch"))
                else:
                    c.execute("UPDATE user SET pin_hash=? WHERE user_id=?", (generate_password_hash(new), user["user_id"]))
                    c.execute("DELETE FROM login_attempt WHERE phone=?", (user["phone"],))
                    c.commit()
                    flash(tr("pin_changed"))
            elif user["role"] == "user":             # only members can delete themselves here
                c.execute("DELETE FROM user WHERE user_id=?", (user["user_id"],))
                c.commit()
                lang = current_lang()
                session.clear()
                session["lang"] = lang
                flash(tr("set_deleted"))
                return redirect(url_for("home"))
        return redirect(url_for("settings"))
    return render_template("settings.html", user=user, languages=sorted(STRINGS))


@app.route("/logout", methods=["POST"])
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


# ---------- facility directory ----------
def facility_filters():
    q = request.args.get("q", "").strip()[:60]
    district = request.args.get("district", "").strip()
    ftype = request.args.get("type", "")
    return q, district, (ftype if ftype in VALID_TYPES else "")


def facility_rows(q, district, ftype, limit=None):
    """Active facilities with how many medicines each reports. Facilities that report stock come first."""
    sql = """SELECT f.*,
                    (SELECT COUNT(*) FROM stock_record s WHERE s.facility_id = f.facility_id) AS n_stock,
                    (SELECT MAX(last_updated) FROM stock_record s WHERE s.facility_id = f.facility_id) AS latest
             FROM facility f WHERE f.is_active = 1"""
    args = []
    if q:
        sql += " AND f.name LIKE ? ESCAPE '\\'"
        args.append(like_pattern(q))
    if district:
        sql += " AND f.district = ?"
        args.append(district)
    if ftype:
        sql += " AND f.type = ?"
        args.append(ftype)
    sql += " ORDER BY (n_stock > 0) DESC, f.name"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return db().execute(sql, args).fetchall()


@app.route("/facilities")
def facilities():
    q, district, ftype = facility_filters()
    rows = facility_rows(q, district, ftype)
    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        page = 1
    pages = max(1, -(-len(rows) // PAGE_SIZE))
    page = min(page, pages)
    S = STRINGS[current_lang()]
    points = [{"lat": r["lat"], "lng": r["lng"], "name": r["name"],
               "status": "listed" if r["n_stock"] else "unlisted",
               "label": S["dir_reports"] if r["n_stock"] else S["dir_no_reports"],
               "med": f"{S['type_' + r['type']]}, {r['district']}",
               "url": url_for("facility", fid=r["facility_id"])}
              for r in rows if r["lat"] is not None and r["lng"] is not None][:500]
    districts = [r[0] for r in db().execute("SELECT DISTINCT district FROM facility WHERE is_active=1 ORDER BY 1")]
    return render_template("facilities.html", rows=rows[(page - 1) * PAGE_SIZE: page * PAGE_SIZE], total=len(rows),
                           page=page, pages=pages, q=q, district=district, ftype=ftype, districts=districts,
                           valid_types=VALID_TYPES, map_points=points,
                           qs={k: v for k, v in (("q", q), ("district", district), ("type", ftype)) if v},
                           map_missing=len(rows) - len(points) if len(rows) > len(points) else 0)


@app.route("/facility/<int:fid>")
def facility(fid):
    f = db().execute("SELECT * FROM facility WHERE facility_id=? AND is_active=1", (fid,)).fetchone()
    if f is None:
        abort(404)
    stock = db().execute("""SELECT m.name, m.strength, m.form, s.quantity, s.last_updated, t.min_quantity
                            FROM stock_record s JOIN medicine m USING (medicine_id)
                            LEFT JOIN alert_threshold t
                              ON t.facility_id = s.facility_id AND t.medicine_id = s.medicine_id
                            WHERE s.facility_id = ? ORDER BY m.name""", (fid,)).fetchall()
    rows = [dict(r, status=compute_status(r["quantity"], r["last_updated"], r["min_quantity"])) for r in stock]
    return render_template("facility.html", f=f, stock=rows)


@app.route("/api/facilities")
def api_facilities():
    """Public, read-only list of facilities (name, type, place, coordinates, phone). Optional ?q= ?district= ?type="""
    q, district, ftype = facility_filters()
    rows = facility_rows(q, district, ftype, limit=500)
    return jsonify({
        "attribution": "Facility data: MedFinder Rwanda and OpenStreetMap contributors (ODbL)",
        "count": len(rows),
        "facilities": [{"id": r["facility_id"], "name": r["name"], "type": r["type"], "district": r["district"],
                        "sector": r["sector"], "lat": r["lat"], "lng": r["lng"], "phone": r["phone"],
                        "opening_hours": r["opening_hours"], "reports_stock": bool(r["n_stock"])} for r in rows]})


# ---------- information pages ----------
def make_info_view(slug):
    def view():
        return render_template("info.html", page=PAGES[slug][current_lang()], slug=slug)
    view.__name__ = f"info_{slug}"
    return view


for _slug in PAGES:                                 # /about /faq /privacy /terms
    app.add_url_rule(f"/{_slug}", endpoint=_slug, view_func=make_info_view(_slug))


@app.route("/contact")
def contact():
    if not any(CONTACT.values()):                   # nothing configured, so there is nothing to show
        abort(404)
    return render_template("contact.html")


@app.errorhandler(404)
def not_found(_e):
    return render_template("error.html", code=404), 404


@app.errorhandler(500)
def server_error(_e):
    return render_template("error.html", code=500), 500


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
                db().execute("INSERT INTO medicine(name,strength,form,aliases) VALUES (?,?,?,?)",
                             (name, request.form.get("strength", "").strip(), request.form.get("form", "").strip(),
                              request.form.get("aliases", "").strip() or None))
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
            db().execute("UPDATE medicine SET name=?, strength=?, form=?, aliases=? WHERE medicine_id=?",
                         (name, request.form.get("strength", "").strip(), request.form.get("form", "").strip(),
                          request.form.get("aliases", "").strip() or None, mid))
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
    # Debug mode shows an interactive console to anyone who can reach the page, so it is opt-in.
    app.run(debug=os.environ.get("MEDFINDER_DEBUG") == "1", use_reloader=False)