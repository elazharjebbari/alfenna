# apps/accounts/components/login/hydrators.py
from django.urls import reverse
from apps.accounts.forms import LoginForm

def login_form(request, params):
    """
    - Reçoit optionnellement un form 'lié' injecté par la vue (pour réafficher les erreurs).
    - Sinon, instancie un LoginForm(request) vierge.
    - Fournit l'URL d’action et la valeur 'next'.
    """
    params = params or {}
    provided = params.get("form")
    form = provided if provided is not None else LoginForm(request)
    action_url = params.get("action_url") or reverse("pages:login")

    return {
        "form": form,
        "action_url": action_url,
        "next_value": request.GET.get("next", ""),
        "headline": params.get("headline"),
        "subline": params.get("subline"),
    }
