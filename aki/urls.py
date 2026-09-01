from django.urls import path

from . import views

app_name = "psnv"

urlpatterns = [
    path("", views.SucheView.as_view(), name="suche"),
    path("angebot/<int:pk>/", views.AngebotDetailView.as_view(), name="angebot_detail"),
    path("einreichen/", views.EinreichenView.as_view(), name="einreichen"),
    path("einreichen/danke/", views.EinreichenDankeView.as_view(), name="einreichen_danke"),
]
