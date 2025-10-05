from __future__ import annotations

from typing import Any, Dict

from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.accounts.forms_signup import SignupForm
from apps.accounts.utils import normalise_form_errors


def _coerce_dict(params: Any) -> Dict[str, Any]:
    return params if isinstance(params, dict) else {}


def _get_form(request, params: dict) -> SignupForm:
    provided = params.get("form")
    if provided is not None:
        return provided  # type: ignore[return-value]
    return SignupForm(request=request, data=request.POST or None)


def _field_value(form: SignupForm, name: str, default: str = "") -> str:
    try:
        bound = form[name]
    except KeyError:
        return default
    value = bound.value()
    if value in (None, "", []):
        return default
    return value


def register_form(request, params):
    data = _coerce_dict(params)
    form = _get_form(request, data)

    field_errors, non_field_errors = normalise_form_errors(form)
    field_errors_text = {k: " ".join(v) for k, v in field_errors.items()}

    return {
        "form": form,
        "action_url": data.get("action_url") or reverse("pages:register"),
        "title": data.get("title") or _("Créer mon compte"),
        "subtitle": data.get("subtitle") or _("Rejoins l’académie en 1 minute."),
        "field_errors": field_errors,
        "field_errors_text": field_errors_text,
        "non_field_errors": non_field_errors,
        "non_field_errors_text": " ".join(non_field_errors),
        "values": {
            "full_name": _field_value(form, "full_name"),
            "email": _field_value(form, "email"),
            "marketing_opt_in": bool(_field_value(form, "marketing_opt_in", "on")),
        },
        "links": {
            "login": data.get("login_url") or reverse("pages:login"),
        },
    }
