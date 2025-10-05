from __future__ import annotations

from typing import Any, Dict

from django.urls import reverse
from django.utils.translation import gettext_lazy as _


def _coerce_dict(params: Any) -> Dict[str, Any]:
    return params if isinstance(params, dict) else {}


def password_reset_done(request, params):
    data = _coerce_dict(params)
    login_url = data.get("login_url") or reverse("pages:login")
    next_value = data.get("next_value")
    links = data.get("links") or []
    if next_value:
        links.append({"url": next_value, "label": data.get("next_label") or _("Retour à la page précédente")})
    links.append({"url": login_url, "label": data.get("login_label") or _("Retour à la connexion")})

    return {
        "title": data.get("title") or _("Vérifie ta boîte mail"),
        "alert_text": data.get("alert_text")
        or _("Si l’adresse existe, un e-mail a été envoyé avec les étapes à suivre."),
        "alert_kind": data.get("alert_kind") or "success",
        "links": links,
    }
