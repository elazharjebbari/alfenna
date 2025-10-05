from django.contrib.auth.forms import PasswordResetForm
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.accounts.utils import resolve_safe_next_url


def password_reset_form(request, params):
    data = params if isinstance(params, dict) else {}
    form = data.get("form")
    if form is None:
        form = PasswordResetForm(request.POST or None)
    next_value = resolve_safe_next_url(request, data.get("next_value"))
    title = data.get("form_title") or data.get("title") or _("Mot de passe oublié")
    subtitle = data.get("form_subtitle") or data.get("subtitle") or _(
        "Renseignez votre adresse e-mail et nous vous enverrons un lien si elle est connue."
    )
    return {
        "form": form,
        "action_url": reverse("accounts:password_reset"),
        "next_value": next_value,
        "form_title": title,
        "form_subtitle": subtitle,
    }


def password_reset_shell(request, params):
    data = params if isinstance(params, dict) else {}
    return {
        "title": data.get("title") or _("Mot de passe oublié"),
        "subtitle": data.get("subtitle")
        or _("Renseignez votre adresse e-mail pour recevoir un lien"),
        "section_classes": data.get("section_classes", "section section-padding"),
        "wrapper_classes": data.get("wrapper_classes", "register-login-wrapper"),
    }
