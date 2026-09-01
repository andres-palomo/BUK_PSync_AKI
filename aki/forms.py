"""
Forms for the PSNV / AKI directory.

Extends the original PsnvAngebotForm (name, description, dienst_typ,
art_betreuung, int_ext) with the pieces needed for a genuinely usable
submission flow:

  - StandortForm gains latitude/longitude (optional) so a submitted Angebot
    can actually be placed on the map.
  - PsnvAngebotForm gains zielgruppen + versorgungsphasen as multi-selects,
    since without at least one Versorgungsphase an Angebot can't show up
    under any of the phase-specific filters.
  - KontaktForm collects the one contact record every Angebot needs.

Phase-specific detail (Verfuegbarkeit, Sprache, etc.) and the remaining
angebot-level tags (Gebiet, Dienste, BOS, Regelversorgung) are intentionally
left to the admin/moderation step (see admin.py) rather than the public
submission form, to keep the public form approachable.
"""

from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Kontakt, PsnvAngebot, Standort, User, Versorgungsphase, Zielgruppe


class SignUpForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email", "phone")


class StandortForm(forms.ModelForm):
    class Meta:
        model = Standort
        fields = [
            "street", "house_number", "zip_code", "city", "region", "state",
            "country", "location_type", "latitude", "longitude",
        ]
        widgets = {
            "latitude": forms.NumberInput(attrs={"step": "any", "placeholder": "z. B. 52.5200"}),
            "longitude": forms.NumberInput(attrs={"step": "any", "placeholder": "z. B. 13.4050"}),
        }
        help_texts = {
            "latitude": "Optional - wird benötigt, damit das Angebot auf der Karte erscheint.",
            "longitude": "Optional - wird benötigt, damit das Angebot auf der Karte erscheint.",
        }


class PsnvAngebotForm(forms.ModelForm):
    zielgruppen = forms.ModelMultipleChoiceField(
        queryset=Zielgruppe.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Zielgruppe(n)",
    )
    versorgungsphasen = forms.ModelMultipleChoiceField(
        queryset=Versorgungsphase.objects.all(),
        required=True,
        widget=forms.CheckboxSelectMultiple,
        label="In welcher(n) Versorgungsphase(n) ist das Angebot aktiv?",
    )

    class Meta:
        model = PsnvAngebot
        fields = ["name", "description", "dienst_typ", "art_betreuung", "int_ext"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }
        labels = {
            "name": "Name des Angebots",
            "description": "Kurzbeschreibung",
            "dienst_typ": "Dienst-Typ",
            "art_betreuung": "Art der Betreuung",
            "int_ext": "Intern / Extern",
        }


class KontaktForm(forms.ModelForm):
    class Meta:
        model = Kontakt
        fields = ["name", "typ", "email", "phone", "phone2", "website"]
        labels = {
            "name": "Ansprechpartner*in",
            "typ": "Kontakt-Typ",
            "phone": "Telefon",
            "phone2": "Telefon (weitere)",
        }
