from __future__ import annotations

from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.accounts.utils import resolve_safe_next_url


def password_reset_complete_message(request, params):
    data = params if isinstance(params, dict) else {}
    next_value = resolve_safe_next_url(request, data.get("next_value"))
    return {
        "title": data.get("title") or _("Mot de passe mis à jour"),
        "description": data.get("description")
        or _("Ton nouveau mot de passe est prêt. Tu peux maintenant te connecter."),
        "next_value": next_value,
        "login_url": data.get("login_url") or reverse("pages:login"),
        "cta_login_label": data.get("cta_login_label") or _("Se connecter"),
        "cta_back_label": data.get("cta_back_label") or _("Retour à la page précédente"),
        "section_classes": data.get("section_classes", "section section-padding"),
        "wrapper_classes": data.get("wrapper_classes", "register-login-wrapper text-center"),
    }
