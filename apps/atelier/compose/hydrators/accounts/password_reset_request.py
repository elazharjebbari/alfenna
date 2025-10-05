from __future__ import annotations

from typing import Any, Dict

from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.accounts.forms_password_reset import OutboxPasswordResetForm
from apps.accounts.utils import normalise_form_errors


def _coerce_dict(params: Any) -> Dict[str, Any]:
    return params if isinstance(params, dict) else {}


def _get_form(request, params: dict) -> OutboxPasswordResetForm:
    provided = params.get("form")
    if provided is not None:
        return provided  # type: ignore[return-value]
    return OutboxPasswordResetForm(request.POST or None)


def password_reset_request_form(request, params):
    data = _coerce_dict(params)
    form = _get_form(request, data)

    field_errors, non_field_errors = normalise_form_errors(form)
    field_errors_text = {k: " ".join(v) for k, v in field_errors.items()}

    return {
        "form": form,
        "action_url": data.get("action_url") or reverse("accounts:password_reset"),
        "title": data.get("title") or _("Mot de passe oublié"),
        "subtitle": data.get("subtitle") or _("Saisis ton e-mail pour recevoir un lien."),
        "field_errors": field_errors,
        "field_errors_text": field_errors_text,
        "non_field_errors": non_field_errors,
        "non_field_errors_text": " ".join(non_field_errors),
        "values": {
            "email": form["email"].value() if "email" in form.fields else "",
        },
        "links": {
            "login": data.get("login_url") or reverse("pages:login"),
        },
    }
