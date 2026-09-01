import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, TemplateView
from django_filters.views import FilterView

from .filters import PsnvAngebotFilter
from .forms import KontaktForm, PsnvAngebotForm, SignUpForm, StandortForm
from .models import AngebotPhase, PsnvAngebot


class SucheView(FilterView):
    """Public search. Only entries a staff member has approved are shown.

    Trivago-style: renders as a list (default) alongside a Leaflet map fed
    by a small JSON payload of the same filtered queryset, so switching
    between list/map on the frontend doesn't need a second request.
    """

    model = PsnvAngebot
    filterset_class = PsnvAngebotFilter
    template_name = "psnv/suche.html"
    context_object_name = "angebot_liste"
    paginate_by = 20

    def get_queryset(self):
        return (
            PsnvAngebot.objects.filter(status=PsnvAngebot.Status.APPROVED, verified=True)
            .select_related("standort")
            .prefetch_related("zielgruppen", "gebiete", "phasen__phase")
            .order_by("name")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Map markers for every filtered result (not just the current page),
        # so the map isn't limited by pagination the way the list is.
        filtered_qs = context["filter"].qs.exclude(standort__latitude__isnull=True).exclude(
            standort__longitude__isnull=True
        )
        markers = [
            {
                "id": angebot.angebot_id,
                "name": angebot.name,
                "lat": angebot.standort.latitude,
                "lng": angebot.standort.longitude,
                "city": angebot.standort.city,
                "dienst_typ": angebot.get_dienst_typ_display(),
                "detail_url": f"/angebot/{angebot.angebot_id}/",
            }
            for angebot in filtered_qs.select_related("standort")
        ]
        context["map_markers_json"] = json.dumps(markers)
        context["result_count"] = context["filter"].qs.count()
        return context


class AngebotDetailView(DetailView):
    model = PsnvAngebot
    template_name = "psnv/angebot_detail.html"
    context_object_name = "angebot"
    pk_url_kwarg = "pk"

    def get_queryset(self):
        qs = PsnvAngebot.objects.select_related("standort", "user").prefetch_related(
            "phasen__phase",
            "phasen__verfuegbarkeiten",
            "phasen__grundausbildungen",
            "phasen__akut_spezialisierungen",
            "phasen__alarm_kanaele",
            "phasen__einzel_o_gruppe_angaben",
            "phasen__grossschaden_erfahrungen",
            "phasen__mitarbeitende_angaben",
            "phasen__finanzierungen",
            "phasen__praeventive_angebote",
            "phasen__sprachen",
            "phasen__kosten_angaben",
            "phasen__psychotraumatologisch_angaben",
            "phasen__taetigkeitsschwerpunkte",
            "zielgruppen",
            "gebiete",
            "dienste",
            "bos",
            "regelversorgung",
            "kontakte",
        )
        if not self.request.user.is_authenticated or not self.request.user.is_staff:
            qs = qs.filter(status=PsnvAngebot.Status.APPROVED, verified=True)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        phasen_by_typ = {ap.phase.typ: ap for ap in self.object.phasen.all()}
        context["phase_praevention"] = phasen_by_typ.get("Praevention")
        context["phase_akut"] = phasen_by_typ.get("Akutversorgung")
        context["phase_regel"] = phasen_by_typ.get("Regelversorgung")
        return context


class EinreichenView(LoginRequiredMixin, TemplateView):
    """
    Submitting a PSNV-Angebot needs three pieces saved together: the
    Standort, the Angebot itself (needs standort_id first), and at least
    one Kontakt + Versorgungsphase link so the entry is actually usable
    once a moderator approves it.
    """

    template_name = "psnv/einreichen_form.html"

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, {
            "angebot_form": PsnvAngebotForm(prefix="angebot"),
            "standort_form": StandortForm(prefix="standort"),
            "kontakt_form": KontaktForm(prefix="kontakt"),
            "titel": "PSNV-Angebot einreichen",
        })

    def post(self, request, *args, **kwargs):
        # Prefixed so the "name" field shared by PsnvAngebotForm and
        # KontaktForm (Angebot name vs. Ansprechpartner*in name) don't
        # collide in the POST data.
        angebot_form = PsnvAngebotForm(request.POST, prefix="angebot")
        standort_form = StandortForm(request.POST, prefix="standort")
        kontakt_form = KontaktForm(request.POST, prefix="kontakt")

        if angebot_form.is_valid() and standort_form.is_valid() and kontakt_form.is_valid():
            with transaction.atomic():
                standort = standort_form.save()

                angebot = angebot_form.save(commit=False)
                angebot.standort = standort
                angebot.user = request.user
                angebot.status = PsnvAngebot.Status.PENDING
                angebot.verified = False
                angebot.save()
                angebot_form.save_m2m()

                for phase in angebot_form.cleaned_data["versorgungsphasen"]:
                    AngebotPhase.objects.create(angebot=angebot, phase=phase)

                kontakt = kontakt_form.save(commit=False)
                kontakt.angebot = angebot
                kontakt.user = None
                kontakt.save()

            messages.success(
                request,
                "Vielen Dank! Ihr Angebot wurde eingereicht und wird nun von unserem Team geprüft.",
            )
            return redirect("psnv:einreichen_danke")

        return render(request, self.template_name, {
            "angebot_form": angebot_form,
            "standort_form": standort_form,
            "kontakt_form": kontakt_form,
            "titel": "PSNV-Angebot einreichen",
        })


class EinreichenDankeView(TemplateView):
    template_name = "psnv/einreichen_danke.html"


class SignUpView(CreateView):
    form_class = SignUpForm
    template_name = "registration/signup.html"
    success_url = reverse_lazy("login")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Konto erstellt. Bitte melden Sie sich an.")
        return response
