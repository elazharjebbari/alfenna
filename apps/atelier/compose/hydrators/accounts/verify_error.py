from __future__ import annotations

from typing import Any, Dict

from django.urls import reverse
from django.utils.translation import gettext_lazy as _


def _coerce_dict(params: Any) -> Dict[str, Any]:
    return params if isinstance(params, dict) else {}


def verify_error(request, params):
    data = _coerce_dict(params)
    resend_url = data.get("resend_url") or reverse("accounts:resend_verification")
    login_url = data.get("login_url") or reverse("pages:login")
    return {
        "title": data.get("title") or _("Lien invalide ou expiré"),
        "alert_text": data.get("message")
        or _("Ce lien de vérification n’est plus valide. Demande un nouvel e-mail."),
        "alert_kind": "error",
        "resend_url": resend_url,
        "resend_label": data.get("cta_label") or _("Renvoyer l’e-mail"),
        "links": data.get("links")
        or [
            {
                "url": login_url,
                "label": data.get("back_label") or _("Retour à la connexion"),
            }
        ],
    }
