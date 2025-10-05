from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.accounts.forms_signup import SignupForm
from apps.accounts.utils import resolve_safe_next_url


def register_form(request, params):
    data = params if isinstance(params, dict) else {}
    form = data.get("form") if isinstance(data, dict) else None
    if form is None:
        form = SignupForm(request=request, data=request.POST or None)
    next_value = resolve_safe_next_url(request, data.get("next_value"))
    title = data.get("form_title") or data.get("title") or _("Créer un compte")
    subtitle = data.get("form_subtitle") or data.get("subtitle") or _("pour accéder aux formations")
    return {
        "form": form,
        "action_url": reverse("accounts:register"),
        "next_value": next_value,
        "form_title": title,
        "form_subtitle": subtitle,
    }


def register_shell(request, params):
    data = params if isinstance(params, dict) else {}
    return {
        "title": data.get("title") or _("Créer un compte"),
        "subtitle": data.get("subtitle") or _("pour accéder aux formations"),
        "show_illustration": data.get("show_illustration", True),
        "section_classes": data.get("section_classes", "section section-padding"),
        "wrapper_classes": data.get("wrapper_classes", "register-login-wrapper"),
        "image_static_path": data.get("image_static_path", "images/login/register-login.png"),
    }
