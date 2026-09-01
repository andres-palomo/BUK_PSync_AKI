from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from . import models


# ---------------------------------------------------------------------------
# Core lookup / tag tables (angebot-level, phase-independent)
# ---------------------------------------------------------------------------

@admin.register(models.Versorgungsphase)
class VersorgungsphaseAdmin(admin.ModelAdmin):
    list_display = ("typ",)


@admin.register(models.Zielgruppe)
class ZielgruppeAdmin(admin.ModelAdmin):
    list_display = ("name", "individuelle_betreuung")
    search_fields = ("name",)


@admin.register(models.OperativePsnv)
class OperativePsnvAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(models.Gebiet)
class GebietAdmin(admin.ModelAdmin):
    list_display = ("name", "region")
    search_fields = ("name", "region")


@admin.register(models.Dienste)
class DiensteAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(models.Bos)
class BosAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(models.Regelversorgung)
class RegelversorgungAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(models.Organisation)
class OrganisationAdmin(admin.ModelAdmin):
    list_display = ("name", "bos_kategorie")
    search_fields = ("name",)


@admin.register(models.Standort)
class StandortAdmin(admin.ModelAdmin):
    list_display = ("__str__", "region", "state", "location_type", "latitude", "longitude")
    search_fields = ("city", "zip_code", "region", "state")
    list_filter = ("location_type", "state")


# ---------------------------------------------------------------------------
# User + Einwilligung
# Einwilligung is tied to User now, not to an Anbieter/Angebot, so it's
# inlined here rather than under PsnvAngebotAdmin.
# ---------------------------------------------------------------------------

class EinwilligungInline(admin.TabularInline):
    model = models.Einwilligung
    extra = 0


@admin.register(models.User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("PSNV/AKI", {"fields": ("organisation", "phone", "verified", "status")}),
    )
    list_display = ("username", "email", "organisation", "verified", "is_staff")
    list_filter = DjangoUserAdmin.list_filter + ("verified", "organisation")
    inlines = [EinwilligungInline]


# ---------------------------------------------------------------------------
# Phase-specific detail tables all FK to AngebotPhase, not to PsnvAngebot
# directly, so they're inlined on AngebotPhaseAdmin (one level down from
# PsnvAngebot) rather than on PsnvAngebotAdmin itself. get_inline_instances
# only shows the inlines relevant to the phase's typ, since e.g. a
# Verfuegbarkeit entry only makes sense under an Akutversorgung phase.
# ---------------------------------------------------------------------------

class FinanzierungInline(admin.TabularInline):
    model = models.Finanzierung
    extra = 1


class PraeventiveAngeboteInline(admin.TabularInline):
    model = models.PraeventiveAngebote
    extra = 1


class VerfuegbarkeitInline(admin.TabularInline):
    model = models.Verfuegbarkeit
    extra = 1


class GrundausbildungInline(admin.TabularInline):
    model = models.Grundausbildung
    extra = 1

class FestformatTrainingInline(admin.TabularInline):
    model = models.FestformatTraining
    extra = 1


class AkutSpezialisierungInline(admin.TabularInline):
    model = models.AkutSpezialisierung
    extra = 1


class AlarmKanalInline(admin.TabularInline):
    model = models.AlarmKanal
    extra = 1


class MitarbeitendeInline(admin.TabularInline):
    model = models.Mitarbeitende
    extra = 1


class EinzelOGruppeInline(admin.TabularInline):
    model = models.EinzelOGruppe
    extra = 1


class GrossschadenErfahrungInline(admin.TabularInline):
    model = models.GrossschadenErfahrung
    extra = 1


class SpracheInline(admin.TabularInline):
    model = models.Sprache
    extra = 1


class KostenInline(admin.TabularInline):
    model = models.Kosten
    extra = 1


class PsychotraumatologischInline(admin.TabularInline):
    model = models.Psychotraumatologisch
    extra = 1


class TaetigkeitsschwerpunktInline(admin.TabularInline):
    model = models.Taetigkeitsschwerpunkt
    extra = 1


PRAEVENTION_INLINES = [FinanzierungInline, PraeventiveAngeboteInline]
AKUTVERSORGUNG_INLINES = [
    VerfuegbarkeitInline, GrundausbildungInline, AkutSpezialisierungInline,
    AlarmKanalInline, MitarbeitendeInline, EinzelOGruppeInline, GrossschadenErfahrungInline,
    FestformatTrainingInline,
]
REGELVERSORGUNG_INLINES = [SpracheInline, KostenInline, PsychotraumatologischInline, TaetigkeitsschwerpunktInline]


@admin.register(models.AngebotPhase)
class AngebotPhaseAdmin(admin.ModelAdmin):
    list_display = ("angebot", "phase")
    list_filter = ("phase",)
    autocomplete_fields = ("angebot",)

    def get_inline_instances(self, request, obj=None):
        if obj is None:
            return []
        by_typ = {
            models.Versorgungsphase.Typ.PRAEVENTION: PRAEVENTION_INLINES,
            models.Versorgungsphase.Typ.AKUTVERSORGUNG: AKUTVERSORGUNG_INLINES,
            models.Versorgungsphase.Typ.REGELVERSORGUNG: REGELVERSORGUNG_INLINES,
        }
        inline_classes = by_typ.get(obj.phase.typ, [])
        return [inline(self.model, self.admin_site) for inline in inline_classes]


# ---------------------------------------------------------------------------
# PsnvAngebot - the moderation queue plus the tag/phase link tables that
# attach directly to it. The six angebot-level tag m2ms all use a custom
# "through" model, so Django admin needs them as inlines rather than
# filter_horizontal (AngebotGebiet also carries an extra "rolle" field).
# ---------------------------------------------------------------------------

class KontaktInline(admin.TabularInline):
    model = models.Kontakt
    extra = 0
    fk_name = "angebot"


class AngebotPhaseInline(admin.TabularInline):
    """Just the Angebot<->Versorgungsphase link. Add phase-specific detail
    (Verfuegbarkeit, Sprache, etc.) on the AngebotPhase's own admin page."""
    model = models.AngebotPhase
    extra = 1
    show_change_link = True


class AngebotZielgruppeInline(admin.TabularInline):
    model = models.AngebotZielgruppe
    extra = 1


class AngebotOperativeInline(admin.TabularInline):
    model = models.AngebotOperative
    extra = 1


class AngebotGebietInline(admin.TabularInline):
    model = models.AngebotGebiet
    extra = 1


class AngebotDiensteInline(admin.TabularInline):
    model = models.AngebotDienste
    extra = 1


class AngebotBosInline(admin.TabularInline):
    model = models.AngebotBos
    extra = 1


class AngebotRegelversorgungInline(admin.TabularInline):
    model = models.AngebotRegelversorgung
    extra = 1


@admin.action(description="Ausgewählte Angebote freigeben (für AKI-Suche sichtbar machen)")
def freigeben(modeladmin, request, queryset):
    queryset.update(status=models.PsnvAngebot.Status.APPROVED, verified=True)


@admin.action(description="Ausgewählte Angebote ablehnen")
def ablehnen(modeladmin, request, queryset):
    queryset.update(status=models.PsnvAngebot.Status.REJECTED, verified=False)


@admin.register(models.PsnvAngebot)
class PsnvAngebotAdmin(admin.ModelAdmin):
    list_display = ("name", "dienst_typ", "art_betreuung", "status", "verified", "user", "created_at")
    list_filter = ("status", "verified", "dienst_typ", "art_betreuung")
    search_fields = ("name", "user__username", "user__email")
    autocomplete_fields = ("user", "standort")
    actions = [freigeben, ablehnen]
    inlines = [
        KontaktInline,
        AngebotPhaseInline,
        AngebotZielgruppeInline,
        AngebotOperativeInline,
        AngebotGebietInline,
        AngebotDiensteInline,
        AngebotBosInline,
        AngebotRegelversorgungInline,
    ]
