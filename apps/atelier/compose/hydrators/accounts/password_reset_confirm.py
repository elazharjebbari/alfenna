from __future__ import annotations

from typing import Any, Dict

from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.accounts.utils import normalise_form_errors


def _coerce_dict(params: Any) -> Dict[str, Any]:
    return params if isinstance(params, dict) else {}


def password_reset_confirm_form(request, params):
    data = _coerce_dict(params)
    form = data.get("form")
    validlink = data.get("validlink", True)

    field_errors, non_field_errors = normalise_form_errors(form) if form is not None else ({}, [])
    field_errors_text = {k: " ".join(v) for k, v in field_errors.items()}

    return {
        "form": form,
        "validlink": validlink,
        "action_url": data.get("action_url") or request.get_full_path(),
        "title": data.get("title") or _("Définir un nouveau mot de passe"),
        "field_errors": field_errors,
        "field_errors_text": field_errors_text,
        "non_field_errors": non_field_errors,
        "non_field_errors_text": " ".join(non_field_errors),
        "links": {
            "request": data.get("request_url") or reverse("accounts:password_reset"),
            "login": data.get("login_url") or reverse("pages:login"),
        },
    }
