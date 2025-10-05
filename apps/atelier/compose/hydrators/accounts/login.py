from __future__ import annotations

from typing import Any, Dict

from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.accounts.forms import LoginForm
from apps.accounts.utils import normalise_form_errors, resolve_safe_next_url


def _coerce_dict(params: Any) -> Dict[str, Any]:
    return params if isinstance(params, dict) else {}


def _get_form(request, params: dict) -> LoginForm:
    provided = params.get("form")
    if provided is not None:
        return provided  # type: ignore[return-value]
    return LoginForm(request=request, data=request.POST or None)


def _field_value(form: LoginForm, name: str, default: Any = "") -> Any:
    try:
        bound = form[name]
    except KeyError:
        return default
    value = bound.value()
    if value in (None, "", []):
        return default
    return value


def login_form(request, params):
    data = _coerce_dict(params)
    form = _get_form(request, data)

    field_errors, non_field_errors = normalise_form_errors(form)
    field_errors_text = {k: " ".join(v) for k, v in field_errors.items()}
    next_value = resolve_safe_next_url(request, data.get("next_value"))

    username_value = _field_value(form, "username", "")
    remember_raw = _field_value(form, "remember_me", "")
    remember_checked = bool(
        (form.cleaned_data.get("remember_me") if hasattr(form, "cleaned_data") else None)
        or remember_raw
    )

    action_url = data.get("action_url") or request.get_full_path() or reverse("pages:login")

    return {
        "form": form,
        "action_url": action_url,
        "next_value": next_value,
        "title": data.get("title") or _("Connexion"),
        "subtitle": data.get("subtitle") or _("Accède à tes cours en toute sécurité."),
        "field_errors": field_errors,
        "field_errors_text": field_errors_text,
        "non_field_errors": non_field_errors,
        "non_field_errors_text": " ".join(non_field_errors),
        "values": {
            "username": username_value,
            "remember_me": remember_checked,
        },
        "links": {
            "forgot": data.get("forgot_url") or reverse("accounts:password_reset"),
            "register": data.get("register_url") or reverse("pages:register"),
        },
    }
