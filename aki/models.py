"""
Models for the PSNV / AKI directory.

Mirrors psnv_schema.dbml table for table, in the same seven sections:

  1. Core entities        - Organisation, Standort, User, PsnvAngebot
  2. Versorgungsphase      - Versorgungsphase + AngebotPhase (n:m Angebot <-> Phase)
  3. Phase-specific detail - one model per phase-specific DBML table, FK'd to
                             AngebotPhase (NOT directly to PsnvAngebot)
  4. Angebot-level tags    - Zielgruppe, OperativePsnv, Gebiet, Dienste, Bos,
                             Regelversorgung + their link tables (angebot-level,
                             phase-independent)
  5. Kontakt               - enforced via CheckConstraint: exactly one of
                             user/angebot is set, never both, never neither
  6. Einwilligung

Two small typos in the DBML enums were fixed while translating them here:
  - Grundausbildung "Allgemeine PSNV Fachausbildung (PSNV-E/B" was missing
    its closing parenthesis (every other option in that enum has one).
  - Psychotraumatologisch's PK column was "Psycotrau_id" in the DBML;
    renamed to psycho_trauma_id here (Python attribute, not a DB rename
    that affects data).

IMPORTANT - custom User model:
  The DBML's User table (first_name, last_name, email, phone, organisation,
  verified, status) maps directly onto Django's AbstractUser plus a few extra
  fields, so User subclasses AbstractUser rather than a separate profile
  model bolted onto auth.User. This requires, in settings.py:

      AUTH_USER_MODEL = "psnv.User"

  ...and it MUST be set before the first makemigrations/migrate for this
  app. If you've already migrated with the default django.contrib.auth.User,
  swapping now needs a fresh dev database rather than a normal migration -
  flag it and we'll work through it rather than risk a half-migrated auth
  table.
"""

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q


# ===========================================================================
# 1. CORE ENTITIES
# ===========================================================================

class Organisation(models.Model):
    class BosKategorie(models.TextChoices):
        POLIZEI = "Polizei", "Polizei"
        FEUERWEHR = "Feuerwehr", "Feuerwehr"
        THW = "THW", "THW"
        SONSTIGE = "BOS-Sonstige", "BOS - Sonstige"

    organisation_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    bos_kategorie = models.CharField(max_length=20, choices=BosKategorie.choices, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "organisation"
        verbose_name = "Organisation"
        verbose_name_plural = "Organisationen"

    def __str__(self):
        return self.name


class Standort(models.Model):
    standort_id = models.AutoField(primary_key=True)
    street = models.CharField("Straße", max_length=255, blank=True)
    house_number = models.CharField("Hausnummer", max_length=20, blank=True)
    zip_code = models.CharField("PLZ", max_length=10, blank=True)
    city = models.CharField("Ort", max_length=255, blank=True)
    region = models.CharField(max_length=255, blank=True)
    state = models.CharField("Bundesland", max_length=255, blank=True)
    country = models.CharField(max_length=100, default="Germany")
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    # Kept as free text per the DBML (which just says varchar, no enum).
    location_type = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "standort"
        indexes = [models.Index(fields=["region", "state", "latitude", "longitude"])]
        verbose_name = "Standort"
        verbose_name_plural = "Standorte"

    def __str__(self):
        parts = [p for p in [self.street, self.zip_code, self.city] if p]
        return ", ".join(parts) or f"Standort {self.standort_id}"


class User(AbstractUser):
    """
    DBML's User table. AbstractUser already provides first_name, last_name,
    email, username, password, is_active, date_joined, etc - only the fields
    the DBML adds on top are declared here.
    """

    organisation = models.ForeignKey(
        Organisation, null=True, blank=True, on_delete=models.SET_NULL, related_name="users",
    )
    phone = models.CharField(max_length=50, blank=True)
    verified = models.BooleanField(default=False)
    status = models.CharField(max_length=50, blank=True)

    class Meta:
        db_table = "user"
        verbose_name = "Nutzer"
        verbose_name_plural = "Nutzer"

    def __str__(self):
        return self.get_full_name() or self.username


class PsnvAngebot(models.Model):
    class DienstTyp(models.TextChoices):
        BERATUNG = "Psychosoziale_Beratung", "Psychosoziale Beratung"
        SOZIALE_DIENSTE = "Soziale_Dienste", "Soziale Dienste"

    class ArtBetreuung(models.TextChoices):
        KLINISCH = "Klinisch", "Klinisch"
        PSYCHOTHERAPEUTISCH = "Psychotherapeutisch", "Psychotherapeutisch"

    class IntExt(models.TextChoices):
        INTERN = "intern", "Intern"
        EXTERN = "extern", "Extern"
        BEIDES = "intern und extern", "Intern und extern"

    # Not an enum in the DBML (just varchar(50)) - added as choices here to
    # drive the moderation workflow your old Anbieter.Status already used.
    # Swap for a plain CharField if you'd rather keep this fully free-form.
    class Status(models.TextChoices):
        PENDING = "pending", "Ausstehend (wartet auf Freigabe)"
        APPROVED = "approved", "Freigegeben"
        REJECTED = "rejected", "Abgelehnt"

    angebot_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="angebote")
    standort = models.ForeignKey(Standort, on_delete=models.PROTECT, related_name="angebote")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    dienst_typ = models.CharField(max_length=30, choices=DienstTyp.choices, blank=True)
    art_betreuung = models.CharField(max_length=30, choices=ArtBetreuung.choices, blank=True)
    int_ext = models.CharField(max_length=20, choices=IntExt.choices, blank=True)
    verified = models.BooleanField(default=False)
    status = models.CharField(max_length=50, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # --- angebot-level classification (phase-independent, see section 4) ---
    zielgruppen = models.ManyToManyField("Zielgruppe", through="AngebotZielgruppe", blank=True, related_name="angebote")
    operative_psnv = models.ManyToManyField("OperativePsnv", through="AngebotOperative", blank=True, related_name="angebote")
    gebiete = models.ManyToManyField("Gebiet", through="AngebotGebiet", blank=True, related_name="angebote")
    dienste = models.ManyToManyField("Dienste", through="AngebotDienste", blank=True, related_name="angebote")
    bos = models.ManyToManyField("Bos", through="AngebotBos", blank=True, related_name="angebote")
    regelversorgung = models.ManyToManyField("Regelversorgung", through="AngebotRegelversorgung", blank=True, related_name="angebote")

    class Meta:
        db_table = "psnv_angebot"
        indexes = [models.Index(fields=["status"])]
        verbose_name = "PSNV-Angebot"
        verbose_name_plural = "PSNV-Angebote"

    def __str__(self):
        return self.name

    @property
    def phasen_typen(self):
        """List of Versorgungsphase.Typ values this Angebot is linked to.

        Convenience for templates (e.g. rendering the phase-track badge on
        search result cards) - relies on `.phasen__phase` being prefetched
        by the calling view to avoid N+1 queries.
        """
        return [ap.phase.typ for ap in self.phasen.all()]


# ===========================================================================
# 2. VERSORGUNGSPHASE
#    A PsnvAngebot can have 1-3 phases (n:m via AngebotPhase). Every
#    phase-specific detail model in section 3 hangs off AngebotPhase, not
#    off PsnvAngebot directly.
# ===========================================================================

class Versorgungsphase(models.Model):
    class Typ(models.TextChoices):
        PRAEVENTION = "Praevention", "Prävention"
        AKUTVERSORGUNG = "Akutversorgung", "Akutversorgung"
        REGELVERSORGUNG = "Regelversorgung", "Regelversorgung"

    phase_id = models.AutoField(primary_key=True)
    typ = models.CharField(max_length=30, choices=Typ.choices, unique=True)

    class Meta:
        db_table = "versorgungsphase"
        verbose_name = "Versorgungsphase"
        verbose_name_plural = "Versorgungsphasen"

    def __str__(self):
        return self.get_typ_display()


class AngebotPhase(models.Model):
    angebot_phase_id = models.AutoField(primary_key=True)
    angebot = models.ForeignKey(PsnvAngebot, on_delete=models.CASCADE, related_name="phasen")
    phase = models.ForeignKey(Versorgungsphase, on_delete=models.CASCADE, related_name="angebot_phasen")

    class Meta:
        db_table = "angebot_phase"
        unique_together = ("angebot", "phase")
        verbose_name = "Angebot × Versorgungsphase"
        verbose_name_plural = "Angebot × Versorgungsphasen"

    def __str__(self):
        return f"{self.angebot} – {self.phase}"


# ===========================================================================
# 3a. PHASENSPEZIFISCH — PRÄVENTION
# ===========================================================================

class Finanzierung(models.Model):
    class Typ(models.TextChoices):
        KOSTENFREI = "Kostenfrei (Verbandsarbeit)", "Kostenfrei (Verbandsarbeit)"
        HONORARBASIS = "Honorarbasis", "Honorarbasis"
        BERUFSGENOSSENSCHAFT = "Berufsgenossenschaft/Unfallkasse", "Berufsgenossenschaft/Unfallkasse"
        ANDERE = "Andere", "Andere"

    fin_id = models.AutoField(primary_key=True)
    angebot_phase = models.ForeignKey(AngebotPhase, on_delete=models.CASCADE, related_name="finanzierungen")
    typ = models.CharField(max_length=50, choices=Typ.choices)
    beschreibung = models.TextField(blank=True)

    class Meta:
        db_table = "finanzierung"
        verbose_name = "Finanzierung"
        verbose_name_plural = "Finanzierungen"

    def __str__(self):
        return f"{self.angebot_phase} – {self.get_typ_display()}"


class PraeventiveAngebote(models.Model):
    class Typ(models.TextChoices):
        NOTFALLPLAENE = "Erstellung_von_Notfallplaenen", "Erstellung von Notfallplänen"
        PSYCHOEDUKATION = "Psychoedukation", "Psychoedukation (Info-Material)"
        RESILIENZTRAINING = "Resilienztraining", "Resilienztraining"
        COACHING = "Coaching_fuer_Fuehrungskraefte", "Coaching für Führungskräfte"
        STRESSMANAGEMENT = "Stressmanagement", "Stressmanagement"
        BELASTENDE_EREIGNISSE = "Umgang_mit_belastenden_Ereignissen", "Umgang mit belastenden Ereignissen"
        SUIZIDPRAEVENTION = "Suizidpraevention", "Suizidprävention"
        DEESKALATIONSTRAINING = "Deeskalationstraining", "Deeskalationstraining"
        ERSTE_HILFE_LAIEN = "Psychische_Erste_Hilfe_fuer_Laien", "Psychische Erste Hilfe für Laien"
        ANDERE = "Andere", "Andere"
        KEINE_ANGABE = "Keine_Angabe", "Keine Angabe"

    praev_id = models.AutoField(primary_key=True)
    angebot_phase = models.ForeignKey(AngebotPhase, on_delete=models.CASCADE, related_name="praeventive_angebote")
    typ = models.CharField(max_length=50, choices=Typ.choices)
    beschreibung = models.TextField(blank=True)

    class Meta:
        db_table = "praeventive_angebote"
        verbose_name = "Präventives Angebot"
        verbose_name_plural = "Präventive Angebote"

    def __str__(self):
        return f"{self.angebot_phase} – {self.get_typ_display()}"


# ===========================================================================
# 3b. PHASENSPEZIFISCH — AKUTVERSORGUNG
# ===========================================================================

class Verfuegbarkeit(models.Model):
    class Typ(models.TextChoices):
        DAUERHAFT = "24/7", "24/7"
        WOCHENTAGE = "Wochentage", "Feste Wochentage"
        SAISONALE = "Saisonale", "Saisonal"
        ANDERE = "Andere", "Andere"

    verf_id = models.AutoField(primary_key=True)
    angebot_phase = models.ForeignKey(AngebotPhase, on_delete=models.CASCADE, related_name="verfuegbarkeiten")
    typ = models.CharField(max_length=20, choices=Typ.choices)
    beschreibung = models.TextField(blank=True)

    class Meta:
        db_table = "verfuegbarkeit"
        verbose_name = "Verfügbarkeit"
        verbose_name_plural = "Verfügbarkeiten"

    def __str__(self):
        return f"{self.angebot_phase} – {self.get_typ_display()}"


class Grundausbildung(models.Model):
    class Typ(models.TextChoices):
        # NOTE: fixed missing closing parenthesis from the DBML source.
        ALLGEMEIN = "Allgemeine PSNV Fachausbildung (PSNV-E/B)", "Allgemeine PSNV Fachausbildung (PSNV-E/B)"
        KRISENINTERVENTION = "Krisenintervention Ausbildung (PSNV-B)", "Krisenintervention Ausbildung (PSNV-B)"
        NOTFALLSEELSORGE = "Notfallseelsorge Ausbildung (PSNV-B)", "Notfallseelsorge Ausbildung (PSNV-B)"
        SBE = "Stressbearbeitung nach belastenden Ereignissen (SbE) (PSNV-E)", "Stressbearbeitung nach belastenden Ereignissen (SbE) (PSNV-E)"
        CISM = "Critical Incident Stress Management (CISM) (PSNV-E)", "Critical Incident Stress Management (CISM) (PSNV-E)"
        PSU = "Psychosoziale Unterstützung (PSU) (PSNV-E)", "Psychosoziale Unterstützung (PSU) (PSNV-E)"
        KEIN_STANDARD = "Kein fester Standard", "Kein fester Standard"
        ANDERE = "Andere", "Andere"

    bildung_id = models.AutoField(primary_key=True)
    angebot_phase = models.ForeignKey(AngebotPhase, on_delete=models.CASCADE, related_name="grundausbildungen")
    typ = models.CharField(max_length=100, choices=Typ.choices)

    class Meta:
        db_table = "grundausbildung"
        verbose_name = "Grundausbildung"
        verbose_name_plural = "Grundausbildungen"

    def __str__(self):
        return f"{self.angebot_phase} – {self.get_typ_display()}"

class FestformatTraining(models.Model):
    festformat_id = models.AutoField(primary_key=True)
    angebot_phase = models.ForeignKey(
        "AngebotPhase", on_delete=models.CASCADE, related_name="festformat_trainings"
    )
    vorhanden = models.BooleanField(
        null=True, blank=True,
        help_text="Gibt es ein festes Format fuer Fortbildungs-/Trainingshistorie? "
                   "None = keine Angabe.",
    )

    class Meta:
        db_table = "festformat_training"
        verbose_name = "Festformat Training"
        verbose_name_plural = "Festformat Trainings"
        # Nur relevant fuer die Versorgungsphase Akutversorgung (wie Grundausbildung).

    def __str__(self):
        if self.vorhanden is None:
            status = "Keine Angabe"
        else:
            status = "Ja" if self.vorhanden else "Nein"
        return f"{self.angebot_phase} - Festformat: {status}"

class AkutSpezialisierung(models.Model):
    class Kategorie(models.TextChoices):
        ZIELGRUPPEN = "Besondere_Zielgruppen", "Besondere Zielgruppen (z. B. Kinder und Jugendliche)"
        EINSATZBEREICHE = "Besondere_Einsatzbereiche", "Besondere Einsatzbereiche (z. B. Seenotrettung)"
        INTERKULTURELL = "Interkulturelle_Kompetenzen", "Interkulturelle Kompetenzen (z. B. Kultur-, religiöse, Fremdsprachenkenntnisse)"

    akut_spez_id = models.AutoField(primary_key=True)
    angebot_phase = models.ForeignKey(AngebotPhase, on_delete=models.CASCADE, related_name="akut_spezialisierungen")
    kategorie = models.CharField(max_length=30, choices=Kategorie.choices)
    vorhanden = models.BooleanField(default=False)
    beschreibung = models.TextField(blank=True)

    class Meta:
        db_table = "akut_spezialisierung"
        unique_together = ("angebot_phase", "kategorie")
        verbose_name = "Fachliche Spezialisierung (Akutversorgung)"
        verbose_name_plural = "Fachliche Spezialisierungen (Akutversorgung)"

    def __str__(self):
        return f"{self.angebot_phase} – {self.get_kategorie_display()}: {'Ja' if self.vorhanden else 'Nein'}"


class AlarmKanal(models.Model):
    class ChannelType(models.TextChoices):
        LEITSTELLE = "Direkt_ueber_Leitstelle", "Direkt über die Leitstelle"
        FUEHRUNG_VOR_ORT = "Ueber_Fuehrungs_oder_Einsatzleitung_vor_Ort", "Über Führungs- oder Einsatzleitung vor Ort"
        ANDERE_ORGANISATIONEN = "Direkt_durch_andere_Organisationen_oder_Dienste", "Direkt durch andere Organisationen oder Dienste"
        INTERNE_STRUKTUREN = "Ueber_interne_Organisationsstrukturen", "Über interne Organisationsstrukturen"
        ANDERE = "Andere", "Andere"
        KEINE_ANGABE = "Keine_Angabe", "Keine Angabe"

    kanal_id = models.AutoField(primary_key=True)
    angebot_phase = models.ForeignKey(AngebotPhase, on_delete=models.CASCADE, related_name="alarm_kanaele")
    channel_type = models.CharField(max_length=60, choices=ChannelType.choices)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "alarm_kanal"
        verbose_name = "Alarmierungskanal"
        verbose_name_plural = "Alarmierungskanäle"

    def __str__(self):
        return f"{self.angebot_phase} – {self.get_channel_type_display()}"


class Mitarbeitende(models.Model):
    mitarbeitende_id = models.AutoField(primary_key=True)
    angebot_phase = models.ForeignKey(AngebotPhase, on_delete=models.CASCADE, related_name="mitarbeitende_angaben")
    zahl = models.TextField(help_text="Freitext, z. B. '18 Ehrenamtliche, 2 Hauptamtliche'")

    class Meta:
        db_table = "mitarbeitende"
        verbose_name = "Mitarbeitende"
        verbose_name_plural = "Mitarbeitende"

    def __str__(self):
        return f"{self.angebot_phase} – {self.zahl}"


class EinzelOGruppe(models.Model):
    class Typ(models.TextChoices):
        EINZELPERSON = "Einzelperson", "Einzelperson"
        GRUPPE = "Gruppe", "Gruppe"
        BEIDES = "Einzelperson oder Gruppe", "Einzelperson oder Gruppe"

    e_o_g_id = models.AutoField(primary_key=True)
    angebot_phase = models.ForeignKey(AngebotPhase, on_delete=models.CASCADE, related_name="einzel_o_gruppe_angaben")
    typ = models.CharField(max_length=30, choices=Typ.choices)

    class Meta:
        db_table = "einzel_o_gruppe"
        verbose_name = "Einzelperson oder Gruppe"
        verbose_name_plural = "Einzelperson-oder-Gruppe-Angaben"

    def __str__(self):
        return f"{self.angebot_phase} – {self.get_typ_display()}"


class GrossschadenErfahrung(models.Model):
    erf_id = models.AutoField(primary_key=True)
    angebot_phase = models.ForeignKey(AngebotPhase, on_delete=models.CASCADE, related_name="grossschaden_erfahrungen")
    ereignis = models.TextField(blank=True)
    ort = models.TextField(blank=True)
    zeitraum_start = models.IntegerField(null=True, blank=True, help_text="Jahr")
    zeitraum_ende = models.IntegerField(null=True, blank=True, help_text="Jahr")
    beschreibung = models.TextField(blank=True)

    class Meta:
        db_table = "grossschaden_erfahrung"
        verbose_name = "Großschadenslagen-Erfahrung"
        verbose_name_plural = "Großschadenslagen-Erfahrungen"

    def __str__(self):
        return f"{self.angebot_phase} – {self.ereignis or self.erf_id}"


# ===========================================================================
# 3c. PHASENSPEZIFISCH — REGELVERSORGUNG
# ===========================================================================

class Sprache(models.Model):
    sprache_id = models.AutoField(primary_key=True)
    angebot_phase = models.ForeignKey(AngebotPhase, on_delete=models.CASCADE, related_name="sprachen")
    name = models.CharField(max_length=100)

    class Meta:
        db_table = "sprache"
        verbose_name = "Sprache"
        verbose_name_plural = "Sprachen"

    def __str__(self):
        return self.name


class Kosten(models.Model):
    class Typ(models.TextChoices):
        JA = "Ja", "Ja"
        NEIN = "Nein", "Nein"

    kosten_id = models.AutoField(primary_key=True)
    angebot_phase = models.ForeignKey(AngebotPhase, on_delete=models.CASCADE, related_name="kosten_angaben")
    typ = models.CharField(max_length=10, choices=Typ.choices)

    class Meta:
        db_table = "kosten"
        verbose_name = "Kosten"
        verbose_name_plural = "Kosten"

    def __str__(self):
        return f"{self.angebot_phase} – {self.get_typ_display()}"


class Psychotraumatologisch(models.Model):
    class Typ(models.TextChoices):
        JA = "Ja", "Ja"
        TEILWEISE = "Teilweise", "Teilweise"
        NEIN = "Nein", "Nein"

    # NOTE: DBML PK column was "Psycotrau_id" (typo) - renamed here.
    psycho_trauma_id = models.AutoField(primary_key=True)
    angebot_phase = models.ForeignKey(AngebotPhase, on_delete=models.CASCADE, related_name="psychotraumatologisch_angaben")
    typ = models.CharField(max_length=10, choices=Typ.choices)

    class Meta:
        db_table = "psychotraumatologisch"
        verbose_name = "Psychotraumatologisch"
        verbose_name_plural = "Psychotraumatologische Angaben"

    def __str__(self):
        return f"{self.angebot_phase} – {self.get_typ_display()}"


class Taetigkeitsschwerpunkt(models.Model):
    class Typ(models.TextChoices):
        PSYCHOTHERAPIE = "Psychologische_Psychotherapie", "Psychologische Psychotherapie"
        SENSIBILISIERUNG = "Sensibilisierung", "Sensibilisierung (z. B. durch Hausarzt)"
        BERATUNG = "Psychosoziale_Beratung", "Psychosoziale Beratung"
        HEILPRAKTIKEN = "Heilpraktiken_der_Psychotherapie", "Heilpraktiken der Psychotherapie"
        TRAUERBEGLEITUNG = "Trauerbegleitung", "Trauerbegleitung"
        EINGLIEDERUNGSHILFE = "Eingliederungshilfe", "Eingliederungshilfe"
        PEER_SUPPORT = "Peer_Support", "Peer-Support"
        ANDERE = "Andere", "Andere"
        KEINE_ANGABE = "Keine_Angabe", "Keine Angabe"

    schwerpunkt_id = models.AutoField(primary_key=True)
    angebot_phase = models.ForeignKey(AngebotPhase, on_delete=models.CASCADE, related_name="taetigkeitsschwerpunkte")
    typ = models.CharField(max_length=50, choices=Typ.choices)
    beschreibung = models.TextField(blank=True)

    class Meta:
        db_table = "taetigkeitsschwerpunkt"
        verbose_name = "Tätigkeitsschwerpunkt"
        verbose_name_plural = "Tätigkeitsschwerpunkte"

    def __str__(self):
        return f"{self.angebot_phase} – {self.get_typ_display()}"


# ===========================================================================
# 4. ANGEBOT-LEVEL KLASSIFIKATION (phase-unabhängig)
#    These attach directly to PsnvAngebot (see the M2M fields declared on it
#    in section 1), not to a specific AngebotPhase.
# ===========================================================================

class Zielgruppe(models.Model):
    ziel_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    individuelle_betreuung = models.BooleanField(default=False)

    class Meta:
        db_table = "zielgruppe"
        verbose_name = "Zielgruppe"
        verbose_name_plural = "Zielgruppen"

    def __str__(self):
        return self.name


class OperativePsnv(models.Model):
    operative_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)

    class Meta:
        db_table = "operative_psnv"
        verbose_name = "Operative PSNV"
        verbose_name_plural = "Operative PSNV"

    def __str__(self):
        return self.name


class Gebiet(models.Model):
    gebiet_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    region = models.CharField(max_length=255, blank=True)
    geometry = models.TextField(blank=True, help_text="GeoJSON, falls vorhanden")

    class Meta:
        db_table = "gebiet"
        verbose_name = "Gebiet"
        verbose_name_plural = "Gebiete"

    def __str__(self):
        return self.name


class Dienste(models.Model):
    dienste_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "dienste"
        verbose_name = "Dienst"
        verbose_name_plural = "Dienste"

    def __str__(self):
        return self.name


class Bos(models.Model):
    bos_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "bos"
        verbose_name = "BOS"
        verbose_name_plural = "BOS"

    def __str__(self):
        return self.name


class Regelversorgung(models.Model):
    """
    Still flagged as a possible overlap with Taetigkeitsschwerpunkt
    (this one is angebot-level, that one is phase-level) - raised earlier
    but not yet resolved. Implemented as-is per the current DBML; revisit
    once you've decided whether to keep both.
    """

    regelversorgung_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "regelversorgung"
        verbose_name = "Regelversorgung"
        verbose_name_plural = "Regelversorgung"

    def __str__(self):
        return self.name


# --- Link tables (n:m, PsnvAngebot <-> classification table) ---

class AngebotZielgruppe(models.Model):
    angebot = models.ForeignKey(PsnvAngebot, on_delete=models.CASCADE)
    zielgruppe = models.ForeignKey(Zielgruppe, on_delete=models.CASCADE)

    class Meta:
        db_table = "angebot_zielgruppe"
        unique_together = ("angebot", "zielgruppe")


class AngebotOperative(models.Model):
    angebot = models.ForeignKey(PsnvAngebot, on_delete=models.CASCADE)
    operative = models.ForeignKey(OperativePsnv, on_delete=models.CASCADE)

    class Meta:
        db_table = "angebot_operative"
        unique_together = ("angebot", "operative")


class AngebotGebiet(models.Model):
    class Rolle(models.TextChoices):
        EINSATZGEBIET = "Einsatzgebiet", "Einsatzgebiet"
        ZUSTAENDIGKEITSGEBIET = "Zuständigkeitsgebiet", "Zuständigkeitsgebiet"

    angebot = models.ForeignKey(PsnvAngebot, on_delete=models.CASCADE)
    gebiet = models.ForeignKey(Gebiet, on_delete=models.CASCADE)
    rolle = models.CharField(max_length=30, choices=Rolle.choices)

    class Meta:
        db_table = "angebot_gebiet"
        unique_together = ("angebot", "gebiet", "rolle")


class AngebotDienste(models.Model):
    angebot = models.ForeignKey(PsnvAngebot, on_delete=models.CASCADE)
    dienste = models.ForeignKey(Dienste, on_delete=models.CASCADE)

    class Meta:
        db_table = "angebot_dienste"
        unique_together = ("angebot", "dienste")


class AngebotBos(models.Model):
    angebot = models.ForeignKey(PsnvAngebot, on_delete=models.CASCADE)
    bos = models.ForeignKey(Bos, on_delete=models.CASCADE)

    class Meta:
        db_table = "angebot_bos"
        unique_together = ("angebot", "bos")


class AngebotRegelversorgung(models.Model):
    angebot = models.ForeignKey(PsnvAngebot, on_delete=models.CASCADE)
    regelversorgung = models.ForeignKey(Regelversorgung, on_delete=models.CASCADE)

    class Meta:
        db_table = "angebot_regelversorgung"
        unique_together = ("angebot", "regelversorgung")


# ===========================================================================
# 5. KONTAKT
# ===========================================================================

class Kontakt(models.Model):
    class Typ(models.TextChoices):
        MAIN = "main", "Haupt"
        SECONDARY = "secondary", "Zweit"
        MOBILE = "mobile", "Mobil"
        FAX = "fax", "Fax"
        OTHER = "other", "Andere"

    kontakt_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name="kontakte")
    angebot = models.ForeignKey(PsnvAngebot, null=True, blank=True, on_delete=models.CASCADE, related_name="kontakte")
    name = models.CharField(max_length=255)
    typ = models.CharField(max_length=20, choices=Typ.choices)
    is_verified = models.BooleanField(default=False)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    phone2 = models.CharField(max_length=50, blank=True)
    website = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "kontakt"
        indexes = [models.Index(fields=["user"]), models.Index(fields=["angebot"])]
        constraints = [
            # Mirrors the DBML note: "Genau eines von user_id / angebot_id ist
            # gesetzt, nie beide, nie keins" - enforced at the DB level here
            # rather than only in application code.
            models.CheckConstraint(
                condition=(
                    Q(user__isnull=False, angebot__isnull=True) |
                    Q(user__isnull=True, angebot__isnull=False)
                ),
                name="kontakt_exactly_one_of_user_or_angebot",
            )
        ]
        verbose_name = "Kontakt"
        verbose_name_plural = "Kontakte"

    def __str__(self):
        return self.name


# ===========================================================================
# 6. EINWILLIGUNG
# ===========================================================================

class Einwilligung(models.Model):
    ein_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="einwilligungen")
    umfrage = models.BooleanField(default=False, help_text="Einwilligung zur Umfrage-Teilnahme")
    aki_sichtbarkeit = models.BooleanField(default=False, help_text="Einwilligung zur Sichtbarkeit im AKI")
    consent_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "einwilligung"
        verbose_name = "Einwilligung"
        verbose_name_plural = "Einwilligungen"

    def __str__(self):
        return f"Einwilligung {self.user} ({self.consent_date})"
