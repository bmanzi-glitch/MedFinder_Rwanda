# MedFinder Rwanda

**Medicine nearby. Health for all.**

MedFinder Rwanda is a web app that tells people which pharmacy, health center or hospital has a medicine in stock, so nobody makes a wasted trip. Facility staff report their stock, patients search it, and administrators watch for low stock, out-of-date data and wrong results.

The site works in **English and Kinyarwanda**, on phones and computers, and also by **SMS and USSD** for people without a smartphone.

> Live demo: https://medfinder-rwanda-awqm.onrender.com
> (free hosting, so the first load after a quiet period can take about a minute)
> Status: working prototype with demo data. Real SMS delivery is not set up yet (see [Known limitations](#known-limitations)).

## What it does

**For patients (no account needed)**
- Search a medicine by name or brand (for example "Panadol" finds Paracetamol), with suggestions as you type.
- Filter by district and facility type, and sort by best match, most recently updated, or nearest.
- See each facility's status (In stock, Low stock, Out of stock, Unverified), when it was last updated, and directions.
- View results as a list or on a map, or use **Use my location** to find the nearest.
- Tell us whether the medicine was really there ("Did you go here?"). This measures the 80% accuracy target.
- Browse the directory of pharmacies and health facilities.

**For facility staff**
- Log in with a phone number and PIN.
- Update the quantity of any medicine in seconds.
- Set a low-stock alert level per medicine and get an SMS when stock falls below it.
- Get a daily SMS reminder when stock has not been updated.

**For managers and administrators**
- Overview with active facilities, low and out-of-stock items, and facilities with out-of-date stock.
- Search accuracy from patient feedback, wasted trips reported, medicines most often out of stock, and searches that found nothing.
- Register facilities, add staff accounts, and manage the medicine catalog (including other names and brands).
- Filter every report by district.

---

## Tech stack

| Part | Choice |
|---|---|
| Language | Python 3 |
| Web framework | Flask 3 (Jinja2 templates) |
| Database | SQLite (single file, `medfinder.db`) |
| Maps | Leaflet 1.9.4 with OpenStreetMap tiles (loaded only when the map tab is opened) |
| Server for production | gunicorn |
| Tests | Python `unittest` and the Flask test client |

---

## Folder structure

```
MedFinder_Rwanda/
├── app.py                    The whole Flask app: routes, search, alerts, SMS/USSD
├── strings.py                All text in English and Kinyarwanda
├── pages.py                  Text of About, FAQ, Privacy and Terms pages
├── schema.sql                Database tables
├── migrate.py                Upgrades an older database in place (makes a backup first)
├── seed.py                   Creates a fresh database with demo data (DELETES the old one)
├── fill_demo_stock.py        Adds every medicine to the demo facilities
├── export_facilities.py      Saves imported pharmacies to facilities_seed.csv
├── load_facilities.py        Loads facilities_seed.csv into the database
├── facilities_seed.csv       478 pharmacies imported from OpenStreetMap
├── import_medicines.py       Loads medicines from a CSV file
├── import_pharmacies.py      Imports facilities from OpenStreetMap
├── medicines_starter.csv     150 starter medicines
├── requirements.txt          Python packages
├── static/
│   └── img/                  Photos, logos and favicons
├── templates/                HTML pages (base.html holds the sidebar and footer)
└── tests/                    Automated tests (43)
```

Files created on your machine and **never committed** (listed in `.gitignore`): `medfinder.db`, database backups (`*.bak-*`), `.secret_key`, `.env`, and the `.venv` folder.

---

## Getting started (Windows, VS Code)

You need Python 3.10 or newer (3.8 and up should also work).

1. **Open the project folder** in VS Code, then open a terminal (Terminal > New Terminal).
2. **Create and activate a virtual environment**
   ```
   python -m venv .venv
   .venv\Scripts\activate
   ```
   On macOS or Linux, use `source .venv/bin/activate`.
3. **Install the packages**
   ```
   pip install -r requirements.txt
   ```
4. **Create the demo database**
   ```
   python seed.py
   ```
   > Warning: `seed.py` **deletes** `medfinder.db` and builds a new one. Run it only when you want to start over.
5. **Load the starter medicines** (150 medicines)
   ```
   python import_medicines.py
   ```
6. **Start the app**
   ```
   python app.py
   ```
   Open <http://127.0.0.1:5000>.

### Demo accounts

| Role | Phone number | PIN |
|---|---|---|
| Administrator | `0788000000` | `admin1` |
| Facility staff (Kimironko Pharmacy) | `0788000001` | `1234` |

Change these before showing the app to anyone outside your team.

---

## Loading data

| Goal | Command |
|---|---|
| Fresh demo database | `python seed.py` |
| Add the 150 starter medicines | `python import_medicines.py` |
| Add your own medicines | `python import_medicines.py my_list.csv` (columns: `name,strength,form,aliases`) |
| Preview any import first | add `--dry-run` |
| Import pharmacies and clinics from OpenStreetMap (Kigali) | `python import_pharmacies.py --dry-run`, then `python import_pharmacies.py` |
| Import other districts | `python import_pharmacies.py --districts Huye,Musanze` |
| Give the 4 demo facilities stock for every medicine | `python fill_demo_stock.py` |
| Keep demo stock "fresh" before a presentation | `python fill_demo_stock.py --refresh` |
| Upgrade an older database | `python migrate.py` |

Notes:
- Imported OpenStreetMap facilities have **no stock** until their staff report it. They appear in the Pharmacies directory, and in medicine search only once they have stock.
- `fill_demo_stock.py` is **demo data only**. It touches facilities 1 to 4 unless you pass `--all` or `--ids`. Do not use it for a real pilot.
- OpenStreetMap coverage is incomplete, so expect fewer places than really exist. Map data is from OpenStreetMap contributors (ODbL licence), credited in the site footer.

---

## How stock status works

| Status | Meaning |
|---|---|
| **In stock** | Quantity at or above the low level, updated in the last 48 hours |
| **Low stock** | Below the facility's alert level, or below 10 if none is set |
| **Out of stock** | Quantity is 0 |
| **Unverified** | Not updated in 48 hours. Patients are told to call before going |

Staff receive a reminder SMS when stock has not been updated in 24 hours. The two limits (`REMINDER_HOURS = 24`, `STALE_HOURS = 48`) are set at the top of `app.py`.

---

## Roles

| Role | Can do |
|---|---|
| Public visitor | Search, browse the directory, give feedback |
| Member (`user`) | Same, plus an account with a saved language |
| Facility staff (`staff`) | Update their own facility's stock and alert levels |
| Manager (`manager`) | See reports only |
| Administrator (`admin`) | Everything: reports, facilities, staff accounts, medicines |

---

## SMS and USSD

MedFinder answers short messages, so people without a smartphone can still check.

- **SMS** (`POST /sms`, field `text`): send `paracetamol Gasabo`, or `rw amoxicillin 250mg Gasabo` for a Kinyarwanda reply. The last word is the district.
- **USSD** (`POST /ussd`, field `text`): choose the language (1 English, 2 Kinyarwanda), then the medicine, then the district.

These endpoints are ready for an SMS and USSD provider such as Africa's Talking. **Sending** SMS (alerts and reminders) is not connected yet. `send_sms()` in `app.py` only writes to the log, and the code is marked with a TODO where the gateway goes.

Send the daily reminders by running this once a day (for example from a scheduled task):

```
flask --app app send-reminders
```

---

## Settings (environment variables)

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Signs login sessions. At least 24 random characters. **Required in production.** On your own machine a key is created automatically in `.secret_key` |
| `MEDFINDER_ENV=production` | Turns on secure cookies and requires `SECRET_KEY` |
| `MEDFINDER_DB` | Path to the database file (default: `medfinder.db` in the project folder) |
| `MEDFINDER_BEHIND_PROXY=1` | Set when running behind nginx or a load balancer |
| `MEDFINDER_DEBUG=1` | Flask debug mode. Never use it on a public server |
| `MEDFINDER_CONTACT_EMAIL`, `MEDFINDER_CONTACT_PHONE`, `MEDFINDER_CONTACT_ADDRESS` | Shown in the footer and on the Contact page. Nothing is shown until you set them |

---

## Running the tests

```
python -m unittest discover -s tests
```

All 43 tests should pass. They cover search, roles and access, stock updates, alerts, accounts, SMS and USSD, and the admin pages.

---

## Deploying

The live demo runs on Render (free plan). Settings used:

- Build command: `pip install -r requirements.txt`
- Start command: `python seed.py && python import_medicines.py && python load_facilities.py && python fill_demo_stock.py --refresh && gunicorn app:app`
- Environment variables: `SECRET_KEY`, `MEDFINDER_ENV=production`, `MEDFINDER_BEHIND_PROXY=1`, `PYTHON_VERSION=3.11.9`

Render's free plan erases files when the service restarts, so the start command rebuilds the demo database each time. Anything entered by hand is lost on restart. For a real pilot, use a host with a persistent disk or a hosted database, and keep `medfinder.db` backed up.

Render blocks the OpenStreetMap import at startup, so pharmacies are saved once from a local database with `python export_facilities.py` and loaded from `facilities_seed.csv`.

## Security and privacy

- PINs are stored as hashes, never as plain text.
- Every form carries a CSRF token. Sessions last 12 hours.
- Failed logins are limited per phone number and per network address, and sign-ups are limited per address.
- Searches log only the query text and district, never personal details.
- Patient feedback stores no personal data.
- Members can delete their own account from Settings.

---

## Known limitations

- Alerts and reminders are created but **not yet delivered by SMS** (no gateway connected).
- Fonts (Google Fonts) and Leaflet (unpkg) load from the internet. Self-hosting them would help on slow or blocked connections.
- There is no screen yet to edit an existing facility's location, and no PIN reset for staff.
- The demo stock is random. Real accuracy figures need real pharmacy data.

---

## Credits

- Map data: © OpenStreetMap contributors.
- Built by Bruce Manzi as an independent project at African Leadership University (PLD 19).
