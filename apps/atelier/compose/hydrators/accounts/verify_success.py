from __future__ import annotations

from typing import Any, Dict

from django.urls import reverse
from django.utils.translation import gettext_lazy as _


def _coerce_dict(params: Any) -> Dict[str, Any]:
    return params if isinstance(params, dict) else {}


def verify_success(request, params):
    data = _coerce_dict(params)
    login_url = data.get("login_url") or reverse("pages:login")
    return {
        "title": data.get("title") or _("Adresse e-mail vérifiée"),
        "alert_text": data.get("message") or _("Ton compte est activé. Tu peux te connecter."),
        "alert_kind": "success",
        "cta_url": login_url,
        "cta_label": data.get("cta_label") or _("Se connecter"),
        "links": data.get("links") or [],
    }
