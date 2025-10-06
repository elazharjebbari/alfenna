# apps/atelier/urls_shim.py
from django.http import HttpResponse
from django.urls import path, reverse, NoReverseMatch
from django.shortcuts import redirect

app_name = None  # IMPORTANT: pas d'app_name pour exposer des noms globaux

def _ok(name):  # petite page neutre
    return HttpResponse(f"OK: {name}", content_type="text/plain")

def register_view(request):
    try:
        return redirect(reverse("accounts:register"))
    except NoReverseMatch:
        try:
            return redirect(reverse("accounts:login"))
        except NoReverseMatch:
            return _ok("register")

def login_view(request):
    try:
        return redirect(reverse("accounts:login"))
    except NoReverseMatch:
        return _ok("login")

def logout_view(request):
    try:
        return redirect(reverse("accounts:logout"))
    except NoReverseMatch:
        return _ok("logout")

def profile_view(request):
    try:
        return redirect(reverse("accounts:profile"))
    except NoReverseMatch:
        return _ok("profile")

urlpatterns = [
    path("register/", register_view, name="register"),
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("profile/", profile_view, name="profile"),
]
