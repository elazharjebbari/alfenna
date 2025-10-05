from django.urls import reverse

from apps.accounts.forms import LoginForm
from apps.accounts.utils import resolve_safe_next_url


def login_form(request, params):
    """Hydrate the login form context for Atelier components."""
    data = params if isinstance(params, dict) else {}
    form = data.get("form")
    if form is None:
        form = LoginForm(request)
    next_value = resolve_safe_next_url(request, data.get("next_value"))
    return {
        "form": form,
        "action_url": reverse("accounts:login"),
        "next_value": next_value,
        "headline": data.get("headline"),
        "subline": data.get("subline"),
    }
