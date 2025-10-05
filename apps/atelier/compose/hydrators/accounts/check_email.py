from __future__ import annotations

from typing import Any, Dict

from django.urls import reverse
from django.utils.translation import gettext_lazy as _


def _coerce_dict(params: Any) -> Dict[str, Any]:
    return params if isinstance(params, dict) else {}


def _obfuscate_email(value: str | None) -> str:
    if not value or "@" not in value:
        return _("ton adresse")
    local, domain = value.split("@", 1)
    local = local.strip()
    domain = domain.strip()
    if not local or not domain:
        return _("ton adresse")
    local_mask = local[0] + "*" * max(len(local) - 2, 1) + local[-1]
    if "." in domain:
        host, tld = domain.split(".", 1)
        host_mask = host[0] + "*" * max(len(host) - 1, 1)
        domain_mask = f"{host_mask}.{tld}"
    else:
        domain_mask = domain[0] + "*" * max(len(domain) - 1, 1)
    return f"{local_mask}@{domain_mask}"


def check_email(request, params):
    data = _coerce_dict(params)
    email = data.get("email")
    obfuscated = data.get("obfuscated_email") or _obfuscate_email(email)
    subtitle_text = data.get("subtitle") or _("Nous venons d’envoyer un lien de confirmation à")
    subtitle_html = f"{subtitle_text} <strong>{obfuscated}</strong>"

    return {
        "title": data.get("title") or _("Vérifie ta boîte mail"),
        "subtitle": subtitle_html,
        "obfuscated_email": obfuscated,
        "description": data.get("description")
        or _("Clique le lien dans l’e-mail pour activer ton compte."),
        "resend_url": data.get("resend_url") or reverse("accounts:resend_verification"),
        "resend_label": data.get("cta_label") or _("Renvoyer l’e-mail"),
        "links": [
            {
                "url": data.get("login_url") or reverse("pages:login"),
                "label": data.get("back_label") or _("Retour à la connexion"),
            }
        ],
    }
