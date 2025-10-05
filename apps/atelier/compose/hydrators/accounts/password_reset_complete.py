from __future__ import annotations

from typing import Any, Dict

from django.urls import reverse
from django.utils.translation import gettext_lazy as _


def _coerce_dict(params: Any) -> Dict[str, Any]:
    return params if isinstance(params, dict) else {}


def password_reset_complete(request, params):
    data = _coerce_dict(params)
    login_url = data.get("login_url") or reverse("pages:login")
    next_value = data.get("next_value")
    if next_value:
        login_url = f"{login_url}?next={next_value}" if "?" not in login_url else login_url

    return {
        "title": data.get("title") or _("Mot de passe mis à jour"),
        "alert_text": data.get("alert_text")
        or _("Ton nouveau mot de passe est enregistré."),
        "alert_kind": data.get("alert_kind") or "success",
        "cta_url": login_url,
        "cta_label": data.get("cta_label") or _("Se connecter"),
        "links": data.get("links") or [],
    }
