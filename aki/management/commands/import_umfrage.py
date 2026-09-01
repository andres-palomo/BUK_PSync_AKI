"""
Management command: import_umfrage

Loads clean_data.csv (verifiziert.csv + oeffentlich.csv, merged/cleaned by
your manager) into the PSNV-Wegweiser models, using the question-ID mapping
worked out from Umfragedatenpunkte.ods.

USAGE
    python manage.py import_umfrage /path/to/clean_data.csv
    python manage.py import_umfrage /path/to/clean_data.csv --dry-run

Put this file at:  psnv/management/commands/import_umfrage.py
(create empty __init__.py files in psnv/management/ and
psnv/management/commands/ if they don't already exist)

DECISIONS BAKED IN (confirmed with Andres 2026-08-20):
  - Every imported PsnvAngebot is attached to ONE shared service User
    (username "umfrage-import"), not a per-respondent account.
  - CONSENT FILTER: a row is only imported at all if DS0_1 == 'Ja' (consent
    to the survey/processing) AND DS0_2 == 'Ja' (consent to appear in AKI).
    Rows that don't clear both are skipped entirely (logged to
    skipped_no_consent.csv), never partially imported as unapproved.
  - Because inclusion already implies consent, ONE shared Einwilligung row
    is created for the service user (umfrage=True, aki_sichtbarkeit=True)
    representing that batch consent - not one per respondent (Einwilligung
    is FK'd to a real User, and there's only the shared one here).
  - status/verified within the consenting rows: 'verifiziert' -> APPROVED /
    verified=True. 'oeffentlich' -> PENDING / verified=False (still needs
    staff review since it wasn't your own outreach).
  - A4 (Zuordnung Angebot) options are split across Bos / OperativePsnv /
    Dienste / Regelversorgung per Andres's scheme (A4_BOS / A4_OPERATIVE /
    A4_DIENSTE / A4_REGELVERSORGUNG below) - NOT matched against the old
    seed rows in those tables, which were fake placeholders. Run with
    --clear-seed-tags once to wipe the placeholder rows first (see below).
  - B4 (further training for the Praevention offering) feeds the SAME
    Grundausbildung model/enum as C3w1k1, just attached to the Praevention
    AngebotPhase instead of Akutversorgung.
  - C7 (Trainingshistorie-Format: has a fixed training-history format,
    yes/no) feeds a NEW model, FestformatTraining - see
    models_addition.py in this delivery. Add it to models.py, register the
    inline in admin.py, then makemigrations/migrate before running this
    command.
"""

import csv
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from aki import models as m


SERVICE_USERNAME = "umfrage-import"

# --- A4: "Unter welchen Oberbegriff faellt Ihr Angebot" -> Andres's fixed
# scheme, confirmed 2026-08-20. Every A4_* option is accounted for below.
A4_BOS = {
    "A4_4": "Bundeswehr", "A4_1": "Feuerwehr", "A4_5": "Hilfsorganisation",
    "A4_2": "Polizei", "A4_3": "Technisches Hilfswerk (THW)",
}
A4_OPERATIVE = {
    "A4_11": "Kriseninterventionsteams (KIT)", "A4_10": "Notfallpsycholog:in",
    "A4_9": "Notfallseelsorge", "A4_13": "PSNV-B Team", "A4_12": "PSNV-E Team",
    "A4_14": "Psychologische Beratung & Soziale Dienste",
}
A4_DIENSTE = {
    "A4_17": "Traumapaedagog:in/ Traumafachberater:in", "A4_18": "Trauerbegleiter:in",
    "A4_19": "Telefonseelsorge", "A4_20": "Schulpsycholog:in & Schulsozialarbeiter:in",
    "A4_21": "Migrations- und Integrationsdienste",
    "A4_22": "Erziehungs- und Familienberatungsstellen (EFB)",
    "A4_23": "Buergertelefon/ Krisenhotlines", "A4_24": "Pfarrer:in",
    "A4_25": "Obdachlosenhilfe", "A4_26": "Behindertenhilfe",
    "A4_27": "Opferhilfestelle (LVR)",
}
A4_REGELVERSORGUNG = {
    "A4_35": "Facharzt:in fuer Psychiatrie und Psychotherapie", "A4_36": "Hausaerzt:in",
    "A4_34": "Kinder- und Jugendpsychotherapeut:in", "A4_33": "Psychiatrische Ambulanz (PIA)",
    "A4_32": "Psychiatrische Klinik", "A4_30": "Psychosomatische Klinik",
    "A4_31": "Psychologische Psychotherapeut:in", "A4_37": "Traumaambulanz",
}

SEED_TAG_MODELS = ["Bos", "OperativePsnv", "Dienste", "Gebiet", "Regelversorgung"]


def ja(row, col):
    return (row.get(col) or "").strip() == "Ja"


def txt(row, col):
    v = (row.get(col) or "").strip()
    return v if v and v != "N. v." else ""


class Command(BaseCommand):
    help = "Import the cleaned Umfrage CSV into PsnvAngebot and related models."

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument("--dry-run", action="store_true", help="Roll back at the end, print counts only.")
        parser.add_argument(
            "--clear-seed-tags", action="store_true",
            help="Delete existing rows in Bos/OperativePsnv/Dienste/Gebiet/Regelversorgung "
                 "before importing (they're fake placeholder seed data, not real values).",
        )

    def handle(self, *args, **opts):
        path = opts["csv_path"]
        dry_run = opts["dry_run"]
        try:
            with open(path, encoding="utf-8-sig") as fh:
                rows = list(csv.DictReader(fh))
        except FileNotFoundError:
            raise CommandError(f"File not found: {path}")

        self.stdout.write(f"Loaded {len(rows)} rows from {path}")

        skipped_log = []
        created_count = 0

        with transaction.atomic():
            if opts["clear_seed_tags"]:
                for model_name in SEED_TAG_MODELS:
                    model = getattr(m, model_name)
                    n, _ = model.objects.all().delete()
                    self.stdout.write(f"  cleared {n} placeholder rows from {model_name}")

            service_user, _ = m.User.objects.get_or_create(
                username=SERVICE_USERNAME,
                defaults={"first_name": "Umfrage", "last_name": "Import", "is_active": False},
            )
            # One shared consent record: inclusion in this import already
            # implies DS0_1 == 'Ja' and DS0_2 == 'Ja' for every row below.
            m.Einwilligung.objects.get_or_create(
                user=service_user,
                defaults={"umfrage": True, "aki_sichtbarkeit": True, "consent_date": date.today()},
            )

            for row in rows:
                if not (txt(row, "DS0_1") == "Ja" and txt(row, "DS0_2") == "Ja"):
                    skipped_log.append({
                        "respondent_id": row.get("id"), "Umfrage": row.get("Umfrage", ""),
                        "DS0_1": txt(row, "DS0_1"), "DS0_2": txt(row, "DS0_2"),
                        "grund": "Kein vollstaendiges Einverstaendnis - nicht importiert",
                    })
                    continue
                angebot = self._import_row(row, service_user)
                created_count += 1
                self.stdout.write(f"  [{row.get('id')}] -> {angebot} (status={angebot.status})")

            if dry_run:
                self.stdout.write(self.style.WARNING("--dry-run: rolling back."))
                transaction.set_rollback(True)

        self._write_review_csv("skipped_no_consent.csv", skipped_log)

        self.stdout.write(self.style.SUCCESS(
            f"Done. {created_count} PsnvAngebot imported, {len(skipped_log)} skipped for missing "
            f"consent (see skipped_no_consent.csv)."
        ))

    # ------------------------------------------------------------------
    def _import_row(self, row, service_user):
        # Caller already guarantees DS0_1 == 'Ja' and DS0_2 == 'Ja' here.
        source = row.get("Umfrage", "").strip()  # 'verifiziert' | 'oeffentlich'
        if source == "verifiziert":
            status, verified = m.PsnvAngebot.Status.APPROVED, True
        else:
            status, verified = m.PsnvAngebot.Status.PENDING, False

        standort = m.Standort.objects.create(
            street=txt(row, "A6_1"),
            zip_code=txt(row, "A6_2").replace(".0", ""),
            city=txt(row, "A6_3"),
            region=txt(row, "A7a"),
        )

        int_ext_map = {"A3w1k1_1": m.PsnvAngebot.IntExt.INTERN, "A3w1k1_2": m.PsnvAngebot.IntExt.EXTERN}
        int_ext = ""
        for col, val in int_ext_map.items():
            if ja(row, col):
                int_ext = val
        if ja(row, "A3w1k1_3"):
            int_ext = m.PsnvAngebot.IntExt.BEIDES

        name = txt(row, "A1a") or txt(row, "A0") or f"Umfrage-Angebot {row.get('id')}"
        angebot = m.PsnvAngebot.objects.create(
            user=service_user, standort=standort, name=name,
            description=txt(row, "A0"), int_ext=int_ext,
            status=status, verified=verified,
        )

        self._import_gebiet(row, angebot)
        self._import_kontakte(row, angebot)
        self._import_a4_tags(row, angebot)
        self._import_phasen(row, angebot)

        return angebot

    def _import_gebiet(self, row, angebot):
        region = txt(row, "A7a")
        if not region:
            return
        gebiet, _ = m.Gebiet.objects.get_or_create(name=region)
        m.AngebotGebiet.objects.get_or_create(
            angebot=angebot, gebiet=gebiet, rolle=m.AngebotGebiet.Rolle.EINSATZGEBIET,
        )
        if ja(row, "A7b_1"):
            m.AngebotGebiet.objects.get_or_create(
                angebot=angebot, gebiet=gebiet, rolle=m.AngebotGebiet.Rolle.ZUSTAENDIGKEITSGEBIET,
            )

    def _import_kontakte(self, row, angebot):
        email, phone, phone2, website = txt(row, "A5a_1"), txt(row, "A5a_2"), txt(row, "A5a_4"), txt(row, "A5a_3")
        if any([email, phone, phone2, website]):
            m.Kontakt.objects.create(
                angebot=angebot, name=angebot.name, typ=m.Kontakt.Typ.MAIN,
                email=email, phone=phone, phone2=phone2, website=website,
            )
        third_name = txt(row, "A5c_5")
        if third_name:
            m.Kontakt.objects.create(
                angebot=angebot, name=third_name, typ=m.Kontakt.Typ.OTHER,
                email=txt(row, "A5c_1"), phone=txt(row, "A5b_2"),
                phone2=txt(row, "A5b_4"), website=txt(row, "A5b_3"),
            )

    def _import_a4_tags(self, row, angebot):
        for col, name in A4_BOS.items():
            if ja(row, col):
                bos, _ = m.Bos.objects.get_or_create(name=name)
                m.AngebotBos.objects.get_or_create(angebot=angebot, bos=bos)
        for col, name in A4_OPERATIVE.items():
            if ja(row, col):
                op, _ = m.OperativePsnv.objects.get_or_create(name=name)
                m.AngebotOperative.objects.get_or_create(angebot=angebot, operative=op)
        for col, name in A4_DIENSTE.items():
            if ja(row, col):
                d, _ = m.Dienste.objects.get_or_create(name=name)
                m.AngebotDienste.objects.get_or_create(angebot=angebot, dienste=d)
        for col, name in A4_REGELVERSORGUNG.items():
            if ja(row, col):
                rv, _ = m.Regelversorgung.objects.get_or_create(name=name)
                m.AngebotRegelversorgung.objects.get_or_create(angebot=angebot, regelversorgung=rv)

    def _link_zielgruppe(self, angebot, name):
        if not name:
            return
        z, _ = m.Zielgruppe.objects.get_or_create(name=name)
        m.AngebotZielgruppe.objects.get_or_create(angebot=angebot, zielgruppe=z)

    # ------------------------------------------------------------------
    def _import_phasen(self, row, angebot):
        if ja(row, "A8_1"):
            self._import_praevention(row, angebot)
        if ja(row, "A8_2"):
            self._import_akutversorgung(row, angebot)
        if ja(row, "A8_3"):
            self._import_regelversorgung(row, angebot)

    def _get_phase(self, angebot, typ):
        phase, _ = m.Versorgungsphase.objects.get_or_create(typ=typ)
        ap, _ = m.AngebotPhase.objects.get_or_create(angebot=angebot, phase=phase)
        return ap

    # Same option set/enum as Grundausbildung (C3w1k1) - B4 asks the same
    # question but for the Praevention offering specifically.
    GRUNDAUSBILDUNG_MAP = {
        "1": m.Grundausbildung.Typ.ALLGEMEIN, "2": m.Grundausbildung.Typ.KRISENINTERVENTION,
        "3": m.Grundausbildung.Typ.NOTFALLSEELSORGE, "4": m.Grundausbildung.Typ.SBE,
        "5": m.Grundausbildung.Typ.CISM, "6": m.Grundausbildung.Typ.PSU,
        "7": m.Grundausbildung.Typ.KEIN_STANDARD, "8": m.Grundausbildung.Typ.ANDERE,
    }

    def _import_praevention(self, row, angebot):
        ap = self._get_phase(angebot, m.Versorgungsphase.Typ.PRAEVENTION)

        if ja(row, "B0k1_1"):
            self._link_zielgruppe(angebot, "Einsatzkraefte")
        if ja(row, "B0k1_2"):
            self._link_zielgruppe(angebot, "Betroffene")

        b1_map = {
            "B1_1": m.PraeventiveAngebote.Typ.NOTFALLPLAENE, "B1_2": m.PraeventiveAngebote.Typ.PSYCHOEDUKATION,
            "B1_3": m.PraeventiveAngebote.Typ.RESILIENZTRAINING, "B1_4": m.PraeventiveAngebote.Typ.COACHING,
            "B1_5": m.PraeventiveAngebote.Typ.STRESSMANAGEMENT, "B1_6": m.PraeventiveAngebote.Typ.BELASTENDE_EREIGNISSE,
            "B1_7": m.PraeventiveAngebote.Typ.SUIZIDPRAEVENTION, "B1_8": m.PraeventiveAngebote.Typ.DEESKALATIONSTRAINING,
            "B1_9": m.PraeventiveAngebote.Typ.ERSTE_HILFE_LAIEN, "B1_10": m.PraeventiveAngebote.Typ.ANDERE,
            "B1_11": m.PraeventiveAngebote.Typ.KEINE_ANGABE,
        }
        for col, typ in b1_map.items():
            if ja(row, col):
                m.PraeventiveAngebote.objects.create(angebot_phase=ap, typ=typ, beschreibung=txt(row, "B1w2"))

        fin_map = {
            "B3w1k1_1": m.Finanzierung.Typ.KOSTENFREI, "B3w1k1_2": m.Finanzierung.Typ.HONORARBASIS,
            "B3w1k1_3": m.Finanzierung.Typ.BERUFSGENOSSENSCHAFT, "B3w1k1_4": m.Finanzierung.Typ.ANDERE,
        }
        for col, typ in fin_map.items():
            if ja(row, col):
                m.Finanzierung.objects.create(angebot_phase=ap, typ=typ, beschreibung=txt(row, "B3w2"))

        # B4: further training for the Praevention offering -> same
        # Grundausbildung model as C3w1k1, attached to this Praevention phase.
        for suffix, typ in self.GRUNDAUSBILDUNG_MAP.items():
            if ja(row, f"B4_{suffix}"):
                m.Grundausbildung.objects.create(angebot_phase=ap, typ=typ)

    def _import_akutversorgung(self, row, angebot):
        ap = self._get_phase(angebot, m.Versorgungsphase.Typ.AKUTVERSORGUNG)

        zahl = txt(row, "C0")
        if zahl:
            m.Mitarbeitende.objects.create(angebot_phase=ap, zahl=zahl)

        eog_map = {"C1k1_1": m.EinzelOGruppe.Typ.EINZELPERSON, "C1k1_2": m.EinzelOGruppe.Typ.GRUPPE}
        for col, typ in eog_map.items():
            if ja(row, col):
                m.EinzelOGruppe.objects.create(angebot_phase=ap, typ=typ)

        if ja(row, "C2k1_1"):
            self._link_zielgruppe(angebot, "Einsatzkraefte")
        if ja(row, "C2k1_2"):
            self._link_zielgruppe(angebot, "Betroffene")

        grund_map = {
            "C3w1k1_1": m.Grundausbildung.Typ.ALLGEMEIN, "C3w1k1_2": m.Grundausbildung.Typ.KRISENINTERVENTION,
            "C3w1k1_3": m.Grundausbildung.Typ.NOTFALLSEELSORGE, "C3w1k1_4": m.Grundausbildung.Typ.SBE,
            "C3w1k1_5": m.Grundausbildung.Typ.CISM, "C3w1k1_6": m.Grundausbildung.Typ.PSU,
            "C3w1k1_7": m.Grundausbildung.Typ.KEIN_STANDARD, "C3w1k1_8": m.Grundausbildung.Typ.ANDERE,
        }
        for col, typ in grund_map.items():
            if ja(row, col):
                m.Grundausbildung.objects.create(angebot_phase=ap, typ=typ)

        spez_map = {
            "C4_1_comment": m.AkutSpezialisierung.Kategorie.ZIELGRUPPEN,
            "C4_2_comment": m.AkutSpezialisierung.Kategorie.EINSATZBEREICHE,
            "C4_3_comment": m.AkutSpezialisierung.Kategorie.INTERKULTURELL,
        }
        for c4_col, kategorie in spez_map.items():
            beschreibung = txt(row, c4_col)
            c5_col = c4_col.replace("C4_", "C5_")
            zusatz = txt(row, c5_col)
            if zusatz:
                beschreibung = f"{beschreibung} | Qualifizierende Weiterbildung: {zusatz}".strip(" |")
            if beschreibung:
                m.AkutSpezialisierung.objects.update_or_create(
                    angebot_phase=ap, kategorie=kategorie,
                    defaults={"vorhanden": True, "beschreibung": beschreibung},
                )

        if ja(row, "C80k1_1"):
            for i in range(1, 6):
                ereignis = txt(row, f"C8_{i}_1")
                if not ereignis:
                    continue
                m.GrossschadenErfahrung.objects.create(
                    angebot_phase=ap, ereignis=ereignis, ort=txt(row, f"C8_{i}_2"),
                    beschreibung=f"{txt(row, f'C8_{i}_3')} - {txt(row, f'C8_{i}_4')}".strip(" -"),
                )

        verf_map = {
            "C9w1k1_1": m.Verfuegbarkeit.Typ.DAUERHAFT, "C9w1k1_2": m.Verfuegbarkeit.Typ.WOCHENTAGE,
            "C9w1k1_3": m.Verfuegbarkeit.Typ.SAISONALE, "C9w1k1_4": m.Verfuegbarkeit.Typ.ANDERE,
        }
        for col, typ in verf_map.items():
            if ja(row, col):
                m.Verfuegbarkeit.objects.create(angebot_phase=ap, typ=typ, beschreibung=txt(row, "C9w2"))

        alarm_map = {
            "C10w1k1_1": m.AlarmKanal.ChannelType.LEITSTELLE, "C10w1k1_2": m.AlarmKanal.ChannelType.FUEHRUNG_VOR_ORT,
            "C10w1k1_3": m.AlarmKanal.ChannelType.ANDERE_ORGANISATIONEN, "C10w1k1_4": m.AlarmKanal.ChannelType.INTERNE_STRUKTUREN,
            "C10w1k1_5": m.AlarmKanal.ChannelType.ANDERE, "C10w1k1_6": m.AlarmKanal.ChannelType.KEINE_ANGABE,
        }
        for col, typ in alarm_map.items():
            if ja(row, col):
                m.AlarmKanal.objects.create(angebot_phase=ap, channel_type=typ, description=txt(row, "C10w2"))

        # C7: "Gibt es ein Format fuer die Fortbildungs- und Trainingshistorie?"
        # New model, Akutversorgung-only, see models_addition.py.
        if ja(row, "C7k1_1"):
            m.FestformatTraining.objects.create(angebot_phase=ap, vorhanden=True)
        elif ja(row, "C7k1_2"):
            m.FestformatTraining.objects.create(angebot_phase=ap, vorhanden=False)

    def _import_regelversorgung(self, row, angebot):
        ap = self._get_phase(angebot, m.Versorgungsphase.Typ.REGELVERSORGUNG)

        schwerpunkt_map = {
            "D0w1k1_1": m.Taetigkeitsschwerpunkt.Typ.PSYCHOTHERAPIE, "D0w1k1_2": m.Taetigkeitsschwerpunkt.Typ.SENSIBILISIERUNG,
            "D0w1k1_3": m.Taetigkeitsschwerpunkt.Typ.BERATUNG, "D0w1k1_11": m.Taetigkeitsschwerpunkt.Typ.HEILPRAKTIKEN,
            "D0w1k1_4": m.Taetigkeitsschwerpunkt.Typ.TRAUERBEGLEITUNG, "D0w1k1_5": m.Taetigkeitsschwerpunkt.Typ.EINGLIEDERUNGSHILFE,
            "D0w1k1_6": m.Taetigkeitsschwerpunkt.Typ.PEER_SUPPORT, "D0w1k1_8": m.Taetigkeitsschwerpunkt.Typ.ANDERE,
            "D0w1k1_9": m.Taetigkeitsschwerpunkt.Typ.KEINE_ANGABE,
        }
        for col, typ in schwerpunkt_map.items():
            if ja(row, col):
                m.Taetigkeitsschwerpunkt.objects.create(angebot_phase=ap, typ=typ, beschreibung=txt(row, "D0w2"))

        if ja(row, "D1k1_1") or ja(row, "D1k1_2"):
            for name in txt(row, "D1a").split(","):
                self._link_zielgruppe(angebot, name.strip())

        if ja(row, "D2k1_1"):
            m.Kosten.objects.create(angebot_phase=ap, typ=m.Kosten.Typ.JA)
        elif ja(row, "D2k1_2"):
            m.Kosten.objects.create(angebot_phase=ap, typ=m.Kosten.Typ.NEIN)

        psycho_map = {
            "D3k1_1": m.Psychotraumatologisch.Typ.NEIN,
            "D3k1_2": m.Psychotraumatologisch.Typ.TEILWEISE, "D3k1_3": m.Psychotraumatologisch.Typ.TEILWEISE,
            "D3k1_4": m.Psychotraumatologisch.Typ.TEILWEISE, "D3k1_5": m.Psychotraumatologisch.Typ.JA,
        }
        for col, typ in psycho_map.items():
            if ja(row, col):
                m.Psychotraumatologisch.objects.create(angebot_phase=ap, typ=typ)

        if ja(row, "D4w1k1_1") or ja(row, "D4w1k1_2"):
            for lang in txt(row, "D4w2").split(","):
                lang = lang.strip()
                if lang:
                    m.Sprache.objects.create(angebot_phase=ap, name=lang)

    # ------------------------------------------------------------------
    def _write_review_csv(self, filename, rows):
        if not rows:
            return
        with open(filename, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        self.stdout.write(f"Wrote {filename} ({len(rows)} rows)")
