from __future__ import annotations

from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.accounts.utils import resolve_safe_next_url


def password_reset_confirm_form(request, params):
    data = params if isinstance(params, dict) else {}
    form = data.get("form")
    next_value = resolve_safe_next_url(request, data.get("next_value"))
    action_url = request.get_full_path() if request is not None else reverse("accounts:password_reset")
    return {
        "form": form,
        "action_url": action_url,
        "next_value": next_value,
        "validlink": data.get("validlink", True),
    }


def password_reset_confirm_shell(request, params):
    data = params if isinstance(params, dict) else {}
    validlink = data.get("validlink", True)
    title = data.get("title") or (
        _("Définir un nouveau mot de passe") if validlink else _("Lien de réinitialisation invalide")
    )
    subtitle = data.get("subtitle") or (
        _("Saisis ton nouveau mot de passe ci-dessous.")
        if validlink
        else _("Ce lien n'est plus valide. Merci de relancer une demande de réinitialisation.")
    )
    return {
        "title": title,
        "subtitle": subtitle,
        "section_classes": data.get("section_classes", "section section-padding"),
        "wrapper_classes": data.get("wrapper_classes", "register-login-wrapper"),
        "validlink": validlink,
    }
