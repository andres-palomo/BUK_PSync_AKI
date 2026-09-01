"""
Seeds the database with realistic-looking German PSNV/AKI demo data so the
app is fully functional out of the box: organisations, users, locations
spread across real German cities (with real coordinates for the map),
PSNV-Angebote in every phase combination, and all the phase-specific detail
tables and angebot-level tag tables.

Usage:
    python manage.py seed_data            # adds to whatever's there
    python manage.py seed_data --flush     # wipes psnv app data first
"""

import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from aki import models as m

try:
    from faker import Faker
except ImportError:  # pragma: no cover
    Faker = None


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

GERMAN_CITIES = [
    # (city, zip, state, region, lat, lon)
    ("Berlin", "10115", "Berlin", "Berlin", 52.5200, 13.4050),
    ("Hamburg", "20095", "Hamburg", "Hamburg", 53.5511, 9.9937),
    ("München", "80331", "Bayern", "Oberbayern", 48.1351, 11.5820),
    ("Köln", "50667", "Nordrhein-Westfalen", "Köln", 50.9375, 6.9603),
    ("Frankfurt am Main", "60311", "Hessen", "Rhein-Main", 50.1109, 8.6821),
    ("Stuttgart", "70173", "Baden-Württemberg", "Stuttgart", 48.7758, 9.1829),
    ("Düsseldorf", "40213", "Nordrhein-Westfalen", "Düsseldorf", 51.2277, 6.7735),
    ("Dortmund", "44135", "Nordrhein-Westfalen", "Ruhrgebiet", 51.5136, 7.4653),
    ("Essen", "45127", "Nordrhein-Westfalen", "Ruhrgebiet", 51.4556, 7.0116),
    ("Leipzig", "04109", "Sachsen", "Leipzig", 51.3397, 12.3731),
    ("Bremen", "28195", "Bremen", "Bremen", 53.0793, 8.8017),
    ("Dresden", "01067", "Sachsen", "Dresden", 51.0504, 13.7373),
    ("Hannover", "30159", "Niedersachsen", "Hannover", 52.3759, 9.7320),
    ("Nürnberg", "90402", "Bayern", "Mittelfranken", 49.4521, 11.0767),
    ("Duisburg", "47051", "Nordrhein-Westfalen", "Ruhrgebiet", 51.4344, 6.7623),
    ("Bochum", "44787", "Nordrhein-Westfalen", "Ruhrgebiet", 51.4818, 7.2162),
    ("Wuppertal", "42103", "Nordrhein-Westfalen", "Bergisches Land", 51.2562, 7.1508),
    ("Bielefeld", "33602", "Nordrhein-Westfalen", "Ostwestfalen-Lippe", 52.0302, 8.5325),
    ("Bonn", "53111", "Nordrhein-Westfalen", "Köln/Bonn", 50.7374, 7.0982),
    ("Münster", "48143", "Nordrhein-Westfalen", "Münsterland", 51.9607, 7.6261),
    ("Mannheim", "68159", "Baden-Württemberg", "Rhein-Neckar", 49.4875, 8.4660),
    ("Karlsruhe", "76133", "Baden-Württemberg", "Karlsruhe", 49.0069, 8.4037),
    ("Augsburg", "86150", "Bayern", "Schwaben", 48.3705, 10.8978),
    ("Wiesbaden", "65183", "Hessen", "Rhein-Main", 50.0782, 8.2398),
    ("Mönchengladbach", "41061", "Nordrhein-Westfalen", "Niederrhein", 51.1805, 6.4428),
    ("Gelsenkirchen", "45879", "Nordrhein-Westfalen", "Ruhrgebiet", 51.5177, 7.0857),
    ("Braunschweig", "38100", "Niedersachsen", "Braunschweig", 52.2689, 10.5268),
    ("Kiel", "24103", "Schleswig-Holstein", "Kiel", 54.3233, 10.1228),
    ("Chemnitz", "09111", "Sachsen", "Chemnitz", 50.8278, 12.9214),
    ("Halle (Saale)", "06108", "Sachsen-Anhalt", "Halle", 51.4825, 11.9699),
    ("Magdeburg", "39104", "Sachsen-Anhalt", "Magdeburg", 52.1205, 11.6276),
    ("Freiburg im Breisgau", "79098", "Baden-Württemberg", "Südbaden", 47.9990, 7.8421),
    ("Rostock", "18055", "Mecklenburg-Vorpommern", "Rostock", 54.0887, 12.1400),
    ("Kassel", "34117", "Hessen", "Nordhessen", 51.3127, 9.4797),
    ("Saarbrücken", "66111", "Saarland", "Saarbrücken", 49.2401, 6.9969),
    ("Mainz", "55116", "Rheinland-Pfalz", "Rheinhessen", 49.9929, 8.2473),
    ("Potsdam", "14467", "Brandenburg", "Potsdam", 52.3906, 13.0645),
    ("Erfurt", "99084", "Thüringen", "Erfurt", 50.9848, 11.0299),
    ("Regensburg", "93047", "Bayern", "Oberpfalz", 49.0134, 12.1016),
    ("Oldenburg", "26122", "Niedersachsen", "Oldenburg", 53.1435, 8.2146),
]

ORG_NAME_TEMPLATES = [
    "Deutsches Rotes Kreuz Kreisverband {city}",
    "Malteser Hilfsdienst {city}",
    "Johanniter-Unfall-Hilfe Regionalverband {city}",
    "Arbeiter-Samariter-Bund {city}",
    "Feuerwehr {city}",
    "Polizeipräsidium {city}",
    "THW Ortsverband {city}",
    "Berufsfeuerwehr {city}",
    "Landesfeuerwehrverband {state}",
    "Notfallseelsorge {city}",
    "Kriseninterventionsteam {city}",
    "PSNV-Verbund {region}",
]

STANDORT_TYPES = ["Hauptsitz", "Regionalstelle", "Geschäftsstelle", "Einsatzzentrale", "Beratungsstelle"]

ZIELGRUPPEN = [
    ("Einsatzkräfte Feuerwehr", True),
    ("Einsatzkräfte Polizei", True),
    ("Einsatzkräfte Rettungsdienst", True),
    ("Einsatzkräfte THW", True),
    ("Führungskräfte", True),
    ("Ehrenamtliche", False),
    ("Angehörige von Einsatzkräften", True),
    ("Auszubildende / Nachwuchskräfte", False),
    ("Zivile Einsatzkräfte / Betroffene", False),
    ("Leitstellendisponent*innen", True),
]

OPERATIVE_PSNV = [
    "Einsatznachsorgeteam (ENT)",
    "Kriseninterventionsteam (KIT)",
    "Peer-Support-Team",
    "Notfallseelsorge-Team",
    "PSU-Team (Psychosoziale Unterstützung)",
    "SbE-Team (Stressbearbeitung nach belastenden Ereignissen)",
]

DIENSTE = [
    ("Telefonseelsorge", "Rund um die Uhr erreichbare telefonische Erstberatung."),
    ("Einzelgespräche", "Vertrauliche Einzelgespräche mit geschulten Fachkräften."),
    ("Gruppenangebote", "Moderierte Gruppenaustausch- und Nachbesprechungsformate."),
    ("Nachsorgegespräche", "Strukturierte Nachbesprechung nach belastenden Einsätzen."),
    ("Supervision", "Regelmäßige fachliche Begleitung für Teams und Einzelpersonen."),
    ("Fortbildungen", "Schulungen zu Stressbewältigung und Selbstfürsorge."),
    ("Onlineberatung", "Beratung per Video oder Chat, ortsunabhängig."),
    ("Aufsuchende Arbeit", "Beratung direkt vor Ort an der Dienststelle oder Wache."),
]

BOS_PARTNERS = [
    ("Leitstelle {region}", "Kooperierende Rettungsleitstelle."),
    ("Feuerwehr {city}", "Kooperierende Feuerwehr."),
    ("Polizeipräsidium {city}", "Kooperierende Polizeidienststelle."),
    ("THW Ortsverband {city}", "Kooperierender THW-Ortsverband."),
    ("Rettungsdienst {region}", "Kooperierender Rettungsdienstträger."),
]

REGELVERSORGUNG = [
    ("Ambulante Psychotherapie", "Regelhafte ambulante psychotherapeutische Versorgung."),
    ("Traumaambulanz", "Spezialisierte ambulante Anlaufstelle nach traumatischen Erlebnissen."),
    ("Beratungsstelle", "Niedrigschwellige psychosoziale Beratungsstelle."),
    ("Klinische Nachsorge", "Weiterbehandlung im Anschluss an eine klinische Akutversorgung."),
    ("Selbsthilfegruppen", "Moderierter Austausch unter Betroffenen."),
    ("Case Management", "Langfristige, koordinierende Begleitung einzelner Fälle."),
]

FIRST_NAMES = ["Anna", "Lukas", "Sabine", "Michael", "Julia", "Thomas", "Laura", "Stefan", "Nina", "Daniel",
               "Katharina", "Markus", "Sophie", "Andreas", "Melanie", "Christian", "Franziska", "Jan", "Petra", "Tobias"]
LAST_NAMES = ["Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker", "Hoffmann", "Schulz",
              "Koch", "Bauer", "Richter", "Klein", "Wolf", "Neumann", "Schwarz", "Zimmermann", "Braun", "Krüger"]

GROSSSCHADEN_EVENTS = [
    ("Hochwasser Ahrtal", "Ahrweiler, Rheinland-Pfalz", 2021, 2021),
    ("Loveparade-Unglück", "Duisburg", 2010, 2010),
    ("Amoklauf", "München", 2016, 2016),
    ("Silvesterkrawalle", "Berlin", 2022, 2023),
    ("Großbrand Industrieanlage", "Leverkusen", 2021, 2021),
    ("Zugunglück", "Bad Aibling", 2016, 2016),
    ("Waldbrand", "Brandenburg", 2022, 2022),
    ("Massenkarambolage A2", "Nordrhein-Westfalen", 2023, 2023),
]

MITARBEITENDE_TEXTS = [
    "12 Ehrenamtliche, 2 Hauptamtliche",
    "25 ausgebildete Peers, koordiniert durch 1 hauptamtliche Leitung",
    "8 Kriseninterventionskräfte im Bereitschaftsdienst",
    "40 Notfallseelsorger*innen im Rotationsdienst",
    "5 Psycholog*innen, 3 Sozialarbeiter*innen",
    "18 ehrenamtliche Einsatzkräfte, 24/7 Rufbereitschaft",
]


def pick(seq):
    return random.choice(seq)


def maybe(seq, p=0.6):
    return random.random() < p


class Command(BaseCommand):
    help = "Seeds the database with demo PSNV/AKI data (organisations, users, angebote, ...)."

    def add_arguments(self, parser):
        parser.add_argument("--flush", action="store_true", help="Delete existing psnv app data before seeding.")
        parser.add_argument("--angebote", type=int, default=60, help="Number of PsnvAngebot to create.")

    def handle(self, *args, **options):
        if Faker is None:
            self.stderr.write(self.style.ERROR("Faker is not installed. `pip install Faker` first."))
            return

        random.seed(42)
        fake = Faker("de_DE")
        Faker.seed(42)

        if options["flush"]:
            self._flush()

        with transaction.atomic():
            self.stdout.write("Erstelle Basis-Referenzdaten ...")
            phasen = self._seed_versorgungsphasen()
            zielgruppen = self._seed_zielgruppen()
            operative = self._seed_operative_psnv()
            gebiete = self._seed_gebiete()
            dienste = self._seed_dienste()
            bos_list = self._seed_bos()
            regelversorgung = self._seed_regelversorgung()

            self.stdout.write("Erstelle Organisationen und Nutzer ...")
            organisationen = self._seed_organisationen(fake)
            users = self._seed_users(fake, organisationen)
            self._seed_einwilligungen(users)
            self._seed_admin_user()

            self.stdout.write(f"Erstelle {options['angebote']} PSNV-Angebote ...")
            self._seed_angebote(
                fake, options["angebote"], users, phasen, zielgruppen, operative,
                gebiete, dienste, bos_list, regelversorgung,
            )

        self.stdout.write(self.style.SUCCESS("Fertig! Datenbank wurde mit Demo-Daten befüllt."))
        self.stdout.write(self.style.SUCCESS("Admin-Login: Benutzername 'admin', Passwort 'psnv-admin-2026'"))

    # -- flush -------------------------------------------------------------

    def _flush(self):
        self.stdout.write("Lösche bestehende Daten ...")
        m.Kontakt.objects.all().delete()
        m.Einwilligung.objects.all().delete()
        for model in [
            m.Finanzierung, m.PraeventiveAngebote, m.Verfuegbarkeit, m.Grundausbildung,
            m.AkutSpezialisierung, m.AlarmKanal, m.Mitarbeitende, m.EinzelOGruppe,
            m.GrossschadenErfahrung, m.Sprache, m.Kosten, m.Psychotraumatologisch,
            m.Taetigkeitsschwerpunkt, m.AngebotPhase,
        ]:
            model.objects.all().delete()
        for model in [
            m.AngebotZielgruppe, m.AngebotOperative, m.AngebotGebiet, m.AngebotDienste,
            m.AngebotBos, m.AngebotRegelversorgung,
        ]:
            model.objects.all().delete()
        m.PsnvAngebot.objects.all().delete()
        m.Standort.objects.all().delete()
        m.Zielgruppe.objects.all().delete()
        m.OperativePsnv.objects.all().delete()
        m.Gebiet.objects.all().delete()
        m.Dienste.objects.all().delete()
        m.Bos.objects.all().delete()
        m.Regelversorgung.objects.all().delete()
        m.Versorgungsphase.objects.all().delete()
        m.User.objects.filter(is_superuser=False).delete()
        m.Organisation.objects.all().delete()

    # -- reference tables ----------------------------------------------------

    def _seed_versorgungsphasen(self):
        return {typ: m.Versorgungsphase.objects.get_or_create(typ=typ)[0] for typ, _ in m.Versorgungsphase.Typ.choices}

    def _seed_zielgruppen(self):
        objs = []
        for name, individuell in ZIELGRUPPEN:
            obj, _ = m.Zielgruppe.objects.get_or_create(name=name, defaults={"individuelle_betreuung": individuell})
            objs.append(obj)
        return objs

    def _seed_operative_psnv(self):
        return [m.OperativePsnv.objects.get_or_create(name=n)[0] for n in OPERATIVE_PSNV]

    def _seed_gebiete(self):
        objs = []
        seen_regions = {c[3] for c in GERMAN_CITIES}
        for region in seen_regions:
            state = next(c[2] for c in GERMAN_CITIES if c[3] == region)
            obj, _ = m.Gebiet.objects.get_or_create(name=region, defaults={"region": state, "geometry": ""})
            objs.append(obj)
        return objs

    def _seed_dienste(self):
        return [m.Dienste.objects.get_or_create(name=n, defaults={"description": d})[0] for n, d in DIENSTE]

    def _seed_bos(self):
        objs = []
        for template, desc in BOS_PARTNERS:
            for _ in range(3):
                city_row = pick(GERMAN_CITIES)
                name = template.format(city=city_row[0], region=city_row[3])
                obj, created = m.Bos.objects.get_or_create(name=name, defaults={"description": desc})
                if created:
                    objs.append(obj)
        return objs or list(m.Bos.objects.all())

    def _seed_regelversorgung(self):
        return [m.Regelversorgung.objects.get_or_create(name=n, defaults={"description": d})[0] for n, d in REGELVERSORGUNG]

    # -- organisations / users -----------------------------------------------

    def _seed_organisationen(self, fake):
        objs = []
        kategorien = [c[0] for c in m.Organisation.BosKategorie.choices]
        for _ in range(18):
            city_row = pick(GERMAN_CITIES)
            template = pick(ORG_NAME_TEMPLATES)
            name = template.format(city=city_row[0], state=city_row[2], region=city_row[3])
            obj, created = m.Organisation.objects.get_or_create(
                name=name,
                defaults={"bos_kategorie": pick(kategorien)},
            )
            if created:
                objs.append(obj)
        return objs or list(m.Organisation.objects.all())

    def _seed_users(self, fake, organisationen):
        users = []
        for i in range(30):
            first = pick(FIRST_NAMES)
            last = pick(LAST_NAMES)
            username = f"{first.lower()}.{last.lower()}{i}"
            if m.User.objects.filter(username=username).exists():
                continue
            user = m.User.objects.create_user(
                username=username,
                email=f"{username}@psnv-demo.de",
                password="demo-passwort-2026",
                first_name=first,
                last_name=last,
                phone=fake.phone_number(),
                organisation=pick(organisationen) if maybe(organisationen, 0.85) else None,
                verified=maybe(None, 0.75),
                status="active",
            )
            users.append(user)
        return users

    def _seed_einwilligungen(self, users):
        for user in users:
            m.Einwilligung.objects.get_or_create(
                user=user,
                defaults={
                    "umfrage": maybe(None, 0.8),
                    "aki_sichtbarkeit": maybe(None, 0.9),
                    "consent_date": date.today() - timedelta(days=random.randint(10, 500)),
                },
            )

    def _seed_admin_user(self):
        if not m.User.objects.filter(username="admin").exists():
            m.User.objects.create_superuser(
                username="admin",
                email="admin@psnv-demo.de",
                password="psnv-admin-2026",
                first_name="Admin",
                last_name="Moderation",
                verified=True,
                status="active",
            )

    # -- angebote --------------------------------------------------------------

    def _seed_angebote(self, fake, count, users, phasen, zielgruppen, operative, gebiete, dienste, bos_list, regelversorgung):
        dienst_typen = [c[0] for c in m.PsnvAngebot.DienstTyp.choices]
        art_betreuungen = [c[0] for c in m.PsnvAngebot.ArtBetreuung.choices]
        int_exts = [c[0] for c in m.PsnvAngebot.IntExt.choices]
        statuses = (
            [m.PsnvAngebot.Status.APPROVED] * 8
            + [m.PsnvAngebot.Status.PENDING] * 1
            + [m.PsnvAngebot.Status.REJECTED] * 1
        )

        name_templates = [
            "Einsatznachsorge {org}",
            "Krisenintervention {city}",
            "PSNV-Team {org}",
            "Notfallseelsorge {city}",
            "Peer-Support {org}",
            "Beratungsstelle für Einsatzkräfte {city}",
            "Psychosoziale Unterstützung {org}",
            "Traumaambulanz {city}",
            "Resilienzzentrum {city}",
            "Fachberatung PSNV {org}",
        ]

        for i in range(count):
            city_row = pick(GERMAN_CITIES)
            city, zip_code, state, region, lat, lon = city_row
            jitter = lambda v: round(v + random.uniform(-0.05, 0.05), 6)

            standort = m.Standort.objects.create(
                street=fake.street_name(),
                house_number=str(random.randint(1, 180)),
                zip_code=zip_code,
                city=city,
                region=region,
                state=state,
                country="Germany",
                latitude=jitter(lat),
                longitude=jitter(lon),
                location_type=pick(STANDORT_TYPES),
            )

            user = pick(users)
            org_name = user.organisation.name if user.organisation else fake.company()
            short_org = org_name.split(" ")[0] if org_name else "PSNV"
            name = pick(name_templates).format(org=short_org, city=city)

            status = pick(statuses)
            angebot = m.PsnvAngebot.objects.create(
                user=user,
                standort=standort,
                name=name,
                description=fake.paragraph(nb_sentences=4),
                dienst_typ=pick(dienst_typen),
                art_betreuung=pick(art_betreuungen),
                int_ext=pick(int_exts),
                verified=(status == m.PsnvAngebot.Status.APPROVED),
                status=status,
            )

            # -- angebot-level tags --------------------------------------------
            for zg in random.sample(zielgruppen, k=random.randint(1, 4)):
                m.AngebotZielgruppe.objects.get_or_create(angebot=angebot, zielgruppe=zg)
            for op in random.sample(operative, k=random.randint(0, 2)):
                m.AngebotOperative.objects.get_or_create(angebot=angebot, operative=op)
            gebiet_choice = next((g for g in gebiete if g.name == region), None) or pick(gebiete)
            m.AngebotGebiet.objects.get_or_create(angebot=angebot, gebiet=gebiet_choice, rolle=pick([c[0] for c in m.AngebotGebiet.Rolle.choices]))
            if maybe(None, 0.4):
                m.AngebotGebiet.objects.get_or_create(angebot=angebot, gebiet=pick(gebiete), rolle=m.AngebotGebiet.Rolle.EINSATZGEBIET)
            for d in random.sample(dienste, k=random.randint(1, 3)):
                m.AngebotDienste.objects.get_or_create(angebot=angebot, dienste=d)
            if bos_list and maybe(None, 0.7):
                for b in random.sample(bos_list, k=min(len(bos_list), random.randint(1, 2))):
                    m.AngebotBos.objects.get_or_create(angebot=angebot, bos=b)
            if maybe(None, 0.5):
                for r in random.sample(regelversorgung, k=random.randint(1, 2)):
                    m.AngebotRegelversorgung.objects.get_or_create(angebot=angebot, regelversorgung=r)

            # -- versorgungsphasen (1-3) + phase-specific detail ---------------
            n_phasen = random.choices([1, 2, 3], weights=[0.35, 0.4, 0.25])[0]
            gewaehlte_phasen = random.sample(list(phasen.values()), k=n_phasen)
            for phase in gewaehlte_phasen:
                ap = m.AngebotPhase.objects.create(angebot=angebot, phase=phase)
                if phase.typ == m.Versorgungsphase.Typ.PRAEVENTION:
                    self._seed_praevention(ap, fake)
                elif phase.typ == m.Versorgungsphase.Typ.AKUTVERSORGUNG:
                    self._seed_akut(ap, fake)
                elif phase.typ == m.Versorgungsphase.Typ.REGELVERSORGUNG:
                    self._seed_regel(ap, fake)

            # -- kontakt ---------------------------------------------------------
            kontakt_name = f"{pick(FIRST_NAMES)} {pick(LAST_NAMES)}"
            m.Kontakt.objects.create(
                angebot=angebot,
                name=kontakt_name,
                typ=m.Kontakt.Typ.MAIN,
                is_verified=maybe(None, 0.7),
                email=f"kontakt@{name.lower().replace(' ', '-')[:40]}.de",
                phone=fake.phone_number(),
                phone2=fake.phone_number() if maybe(None, 0.3) else "",
                website=f"https://www.{name.lower().replace(' ', '')[:30]}.de" if maybe(None, 0.6) else "",
            )
            if maybe(None, 0.25):
                m.Kontakt.objects.create(
                    angebot=angebot,
                    name=f"{pick(FIRST_NAMES)} {pick(LAST_NAMES)}",
                    typ=pick([m.Kontakt.Typ.SECONDARY, m.Kontakt.Typ.MOBILE]),
                    is_verified=False,
                    phone=fake.phone_number(),
                )

    # -- phase-specific detail builders -----------------------------------------

    def _seed_praevention(self, ap, fake):
        for typ, _ in random.sample(m.Finanzierung.Typ.choices, k=random.randint(1, 2)):
            m.Finanzierung.objects.create(angebot_phase=ap, typ=typ, beschreibung=fake.sentence())
        for typ, _ in random.sample(m.PraeventiveAngebote.Typ.choices, k=random.randint(1, 3)):
            m.PraeventiveAngebote.objects.create(angebot_phase=ap, typ=typ, beschreibung=fake.sentence())

    def _seed_akut(self, ap, fake):
        for typ, _ in random.sample(m.Verfuegbarkeit.Typ.choices, k=random.randint(1, 2)):
            m.Verfuegbarkeit.objects.create(angebot_phase=ap, typ=typ, beschreibung=fake.sentence() if maybe(None, 0.5) else "")
        for typ, _ in random.sample(m.Grundausbildung.Typ.choices, k=random.randint(1, 2)):
            m.Grundausbildung.objects.create(angebot_phase=ap, typ=typ)
        for kategorie, _ in m.AkutSpezialisierung.Kategorie.choices:
            if maybe(None, 0.5):
                m.AkutSpezialisierung.objects.create(
                    angebot_phase=ap, kategorie=kategorie, vorhanden=maybe(None, 0.6),
                    beschreibung=fake.sentence() if maybe(None, 0.5) else "",
                )
        for typ, _ in random.sample(m.AlarmKanal.ChannelType.choices, k=random.randint(1, 2)):
            m.AlarmKanal.objects.create(angebot_phase=ap, channel_type=typ)
        m.Mitarbeitende.objects.create(angebot_phase=ap, zahl=pick(MITARBEITENDE_TEXTS))
        m.EinzelOGruppe.objects.create(angebot_phase=ap, typ=pick([c[0] for c in m.EinzelOGruppe.Typ.choices]))
        if maybe(None, 0.4):
            event = pick(GROSSSCHADEN_EVENTS)
            m.GrossschadenErfahrung.objects.create(
                angebot_phase=ap, ereignis=event[0], ort=event[1],
                zeitraum_start=event[2], zeitraum_ende=event[3],
                beschreibung=fake.sentence(),
            )

    def _seed_regel(self, ap, fake):
        sprachen = random.sample(["Deutsch", "Englisch", "Türkisch", "Polnisch", "Russisch", "Arabisch", "Französisch"], k=random.randint(1, 3))
        for s in sprachen:
            m.Sprache.objects.create(angebot_phase=ap, name=s)
        m.Kosten.objects.create(angebot_phase=ap, typ=pick([c[0] for c in m.Kosten.Typ.choices]))
        m.Psychotraumatologisch.objects.create(angebot_phase=ap, typ=pick([c[0] for c in m.Psychotraumatologisch.Typ.choices]))
        for typ, _ in random.sample(m.Taetigkeitsschwerpunkt.Typ.choices, k=random.randint(1, 3)):
            m.Taetigkeitsschwerpunkt.objects.create(angebot_phase=ap, typ=typ, beschreibung=fake.sentence() if maybe(None, 0.4) else "")
