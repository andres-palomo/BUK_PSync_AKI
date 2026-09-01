from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from aki.views import SignUpView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("konto/registrieren/", SignUpView.as_view(), name="signup"),
    path("konto/anmelden/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("konto/abmelden/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("aki.urls")),
]
