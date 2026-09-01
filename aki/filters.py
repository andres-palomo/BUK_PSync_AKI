import django_filters
from django import forms
from django.db.models import Q

from .models import AkutSpezialisierung, Gebiet, PsnvAngebot, Versorgungsphase, Zielgruppe


class PsnvAngebotFilter(django_filters.FilterSet):
    """
    Drives the public search: dienst_typ, Zielgruppe, Versorgungsphase,
    Gebiet, PSNV-Stufe, Fachliche Spezialisierung, and free-text location
    (city / PLZ).

    NOTE: PsnvAngebot now carries its own standort_id directly (no more
    Team indirection), so the "ort" lookup goes through .standort straight
    away instead of .team.standort.

    grundausbildung_stufe / akut_spezialisierungen both reach into
    Akutversorgung-phase detail tables (Grundausbildung, AkutSpezialisierung)
    that hang off AngebotPhase, not off PsnvAngebot directly - hence the
    `phasen__...` path and the explicit `.distinct()` in each method filter
    (a join across a multi-valued relation can otherwise return the same
    PsnvAngebot more than once).
    """

    PSNV_STUFE_CHOICES = (
        ("PSNV-B", "PSNV-B (Betreuung)"),
        ("PSNV-E", "PSNV-E (Einsatzkräfte)"),
    )

    name = django_filters.CharFilter(
        field_name="name", lookup_expr="icontains", label="Name / Stichwort",
    )
    dienst_typ = django_filters.ChoiceFilter(
        choices=PsnvAngebot.DienstTyp.choices, label="Dienst-Typ",
    )
    zielgruppen = django_filters.ModelMultipleChoiceFilter(
        queryset=Zielgruppe.objects.all(),
        label="Zielgruppe",
        widget=forms.CheckboxSelectMultiple,
    )
    versorgungsphasen = django_filters.ModelMultipleChoiceFilter(
        field_name="phasen__phase",
        queryset=Versorgungsphase.objects.all(),
        label="Versorgungsphase",
        widget=forms.CheckboxSelectMultiple,
        distinct=True,  # avoid duplicate rows from the AngebotPhase join
    )
    grundausbildung_stufe = django_filters.ChoiceFilter(
        choices=PSNV_STUFE_CHOICES,
        method="filter_grundausbildung_stufe",
        label="PSNV-Stufe (Grundausbildung)",
    )
    akut_spezialisierungen = django_filters.MultipleChoiceFilter(
        choices=AkutSpezialisierung.Kategorie.choices,
        method="filter_akut_spezialisierung",
        label="Fachliche Spezialisierung",
        widget=forms.CheckboxSelectMultiple,
    )
    gebiete = django_filters.ModelMultipleChoiceFilter(
        field_name="gebiete",
        queryset=Gebiet.objects.all(),
        label="Gebiet",
        widget=forms.CheckboxSelectMultiple,
    )
    ort = django_filters.CharFilter(
        method="filter_ort", label="Ort oder PLZ",
    )

    class Meta:
        model = PsnvAngebot
        fields = [
            "name", "dienst_typ", "zielgruppen", "versorgungsphasen",
            "grundausbildung_stufe", "akut_spezialisierungen", "gebiete", "ort",
        ]

    def filter_ort(self, queryset, name, value):
        return queryset.filter(
            Q(standort__city__icontains=value) | Q(standort__zip_code__icontains=value)
        )

    def filter_grundausbildung_stufe(self, queryset, name, value):
        if not value:
            return queryset
        # Grundausbildung.typ values embed the stufe in the label itself,
        # e.g. "Notfallseelsorge Ausbildung (PSNV-B)". The one generic
        # "Allgemeine PSNV Fachausbildung (PSNV-E/B)" option covers both
        # stufen at once, so it's matched for either filter value.
        return queryset.filter(
            Q(phasen__grundausbildungen__typ__icontains=value)
            | Q(phasen__grundausbildungen__typ__icontains="PSNV-E/B")
        ).distinct()

    def filter_akut_spezialisierung(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            phasen__akut_spezialisierungen__kategorie__in=value,
            phasen__akut_spezialisierungen__vorhanden=True,
        ).distinct()
