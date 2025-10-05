# accounts/utils.py
from __future__ import annotations

from django.contrib.auth.models import User
from django.forms.forms import NON_FIELD_ERRORS as FORM_NON_FIELD_ERRORS
from django.utils.http import url_has_allowed_host_and_scheme

from .models import StudentProfile

def resolve_safe_next_url(request, candidate: str | None = None) -> str:
    """Return a safe ``next`` URL limited to the current host."""
    if request is None:
        return ""

    next_url = candidate or request.POST.get("next") or request.GET.get("next")
    if not next_url:
        return ""

    is_secure = request.is_secure() if hasattr(request, "is_secure") else False
    if url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=is_secure,
    ):
        return next_url
    return ""


def normalise_form_errors(form):
    """Return (field_errors, non_field_errors) for a Django form."""
    field_errors: dict[str, list[str]] = {}
    non_field_errors: list[str] = []

    if not getattr(form, 'errors', None):
        return field_errors, non_field_errors

    for field_name, errors in form.errors.items():
        messages = [str(err) for err in errors]
        if field_name in (FORM_NON_FIELD_ERRORS, '__all__'):
            non_field_errors.extend(messages)
        else:
            field_errors[field_name] = messages
    return field_errors, non_field_errors


def ensure_profiles():
    """
    Vérifie que chaque User a bien un StudentProfile.
    Crée les manquants si nécessaire.
    """
    for user in User.objects.all():
        StudentProfile.objects.get_or_create(user=user)
