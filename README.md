# PSync_AKI (PSNV-Wegweiser)

A "Trivago-style" search and directory platform for psychosocial emergency
care (PSNV) for first responders — list/map views, filters (Zielgruppe,
Versorgungsphase, Gebiet, Dienst-Typ, PSNV-Stufe, Fachliche Spezialisierung,
location), and a submission workflow for new offers that a moderator
approves via the Django admin.

The data model (`aki/models.py`) is a direct implementation of the
project's DBML schema, grouped into the same seven sections as the schema
itself.

**Folder notes:**

- The Django app lives in `aki/` (not `psnv/` or `apps/`). Internally, the
  URL namespace is still `psnv` (e.g. `{% url 'psnv:suche' %}` in
  templates) — that's just a routing label, unrelated to the app's folder
  name, so it didn't need to change.
- Static files live at `aki/static/aki/css/style.css` — that's Django's
  standard per-app static file layout (`<app>/static/<app_name>/...`),
  which is why the inner folder is also named `aki`: it's what keeps
  `{% static 'aki/css/style.css' %}` resolving to the right file if this
  project ever has more than one app. Django finds it automatically
  (`AppDirectoriesFinder`, on by default) — no `STATICFILES_DIRS` entry is
  needed for it.

## Quick start

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py runserver

## to import csv data
python manage.py import_umfrage <path_to_csv> --clear-seed-tags --dry-run

## To remove the old fake Angebote (keeping only what came from the survey import):
python manage.py shell -c "from aki.models import PsnvAngebot as P; P.objects.exclude(user__username='umfrage-import').delete()"
```

Then open <http://127.0.0.1:8000/>. The bundled `db.sqlite3` is already
migrated and pre-seeded with demo data, so no `migrate`/`seed_data` step is
required to look at it.

## Login credentials (demo data)

| Role | Username | Password |
|---|---|---|
| Admin / moderation (`/admin/`) | `admin` | `psnv-admin-2026` |
| Regular user (can submit offers) | e.g. `anna.mueller0` (run `python manage.py shell` → `User.objects.values_list("username")` to see all) | `demo-passwort-2026` |

All demo users share the password `demo-passwort-2026`.

## Pages / features

- **`/`** — Public search: filter sidebar (name, Ort/PLZ, Dienst-Typ,
  PSNV-Stufe, Versorgungsphase, Zielgruppe, Fachliche Spezialisierung,
  Gebiet) + list/map view (Leaflet / OpenStreetMap, no API key needed).
  Only approved (`status=approved`, `verified=True`) Angebote are visible.
- **`/angebot/<id>/`** — Detail page with every phase-specific field,
  classification, contact info, and a mini map.
- **`/einreichen/`** — Login-gated submission form (Angebot + Standort +
  Kontakt + Versorgungsphase(n)). New Angebote land as `status=pending`
  and need approval in the admin.
- **`/admin/`** — Moderation UI: approve/reject bulk actions on the Angebot
  list, nested inlines for every phase-specific and Angebot-wide detail
  table. (Admin URLs live under `/admin/aki/...`, matching the `aki/`
  folder name.)
- **`/konto/registrieren/`, `/konto/anmelden/`** — Registration/login.

## Regenerating demo data

```bash
python manage.py seed_data --flush --angebote 65
```

`--flush` deletes everything the seed script previously created before
generating fresh data. `--angebote` controls how many PSNV-Angebote get
created (default: 60).

## Files not included here

A few paths in this project structure are owned by other parts of the
team's workflow and were intentionally **not** filled in with guessed
content:

- `data/raw/oeffentlich.csv`, `data/raw/verifiziert.csv`
- `aki/management/commands/process_data.py`
- `aki/scripts/aktualisiere_git.sh`
- `AKI_Strukturplan_erweitert.xlsx`

Each has either a placeholder file explaining what belongs there, or (for
the xlsx) a `.PLACEHOLDER.txt` note at the project root. Drop the real
files in from the original project; nothing else in the app depends on
their content being any particular way except `process_data.py`, if it's
meant to load `data/raw/*.csv` into the database — worth checking its
original logic against `aki/models.py` once it's back in place.

## PostgreSQL / Docker

An earlier version of this project (with the same app-folder structure)
also supported running against PostgreSQL, via Docker Compose or a
manually configured Postgres server, with zero code changes needed beyond
environment variables. That version was set aside for now in favor of this
simpler SQLite-only setup, but the settings.py changes needed to bring it
back are small and can be re-added if useful later.

## Known open items (carried over from the schema/code comments)

- `Regelversorgung` (Angebot-wide) and `Taetigkeitsschwerpunkt`
  (phase-specific) may cover the same underlying concept — flagged as an
  open question in the original schema, implemented here as two separate
  tables as-is.
- The public submission form deliberately doesn't cover every
  phase-specific detail table (e.g. Verfügbarkeit, Sprachen) — that
  currently happens in the admin after submission, to keep the public form
  approachable.
