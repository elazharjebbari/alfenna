from __future__ import annotations
from django.urls import reverse, NoReverseMatch
from django.utils.translation import gettext as _

def _rev(name: str, default: str | None = None) -> str | None:
    try:
        return reverse(name)
    except NoReverseMatch:
        return default

def login_modal(request, params):
    """
    Construit le contexte du modal de connexion en acceptant des overrides via `params`.
    Valeurs par défaut compatibles avec ton backend:
      - POST -> pages:login (LoginViewSafe)
      - champs: username, password, remember_me, next
    """
    p = params or {}

    # URLs
    action_url = p.get("action_url") or _rev("pages:login", "/accounts/login/")
    next_url   = p.get("next_url") or request.GET.get("next") or request.get_full_path()

    # Liens auxiliaires (best-effort: certains endpoints peuvent ne pas exister)
    register_url = p.get("register_url") or _rev("accounts:register", None) or _rev("accounts:signup", None)
    forgot_url   = p.get("forgot_url")   or _rev("accounts:password_reset", None)

    # Apparence + libellés
    ctx = {
        "dom_id":                p.get("dom_id", "loginModal"),
        "method":                p.get("method", "post"),
        "action_url":            action_url,
        "next_url":              next_url,
        "hidden_fields":         p.get("hidden_fields") or {},

        "title":                 p.get("title") or _("Se connecter"),
        "description":           p.get("description") or "",
        "username_label":        p.get("username_label") or _("Email ou nom d'utilisateur"),
        "password_label":        p.get("password_label") or _("Mot de passe"),
        "remember_label":        p.get("remember_label") or _("Rester connecté"),
        "submit_label":          p.get("submit_label") or _("Se connecter"),
        "register_label":        p.get("register_label") or _("S'inscrire"),
        "forgot_label":          p.get("forgot_label") or _("Mot de passe oublié ?"),

        "username_placeholder":  p.get("username_placeholder") or "",
        "password_placeholder":  p.get("password_placeholder") or "",

        "show_register":         p.get("show_register", True if register_url else False),
        "register_url":          register_url,
        "show_forgot":           p.get("show_forgot", True if forgot_url else False),
        "forgot_url":            forgot_url,

        "dialog_class":          p.get("dialog_class", "modal-dialog"),
        "content_class":         p.get("content_class", "border-0 shadow-sm"),
        "header_class":          p.get("header_class", ""),
        "body_class":            p.get("body_class", ""),
        "footer_class":          p.get("footer_class", ""),
        "close_btn_class":       p.get("close_btn_class", ""),
        "submit_btn_class":      p.get("submit_btn_class", "btn btn-primary"),
        "register_btn_class":    p.get("register_btn_class", "btn btn-link"),
        "forgot_link_class":     p.get("forgot_link_class", "link-secondary small"),
        "username_input_class":  p.get("username_input_class", ""),
        "password_input_class":  p.get("password_input_class", ""),
        "remember_input_class":  p.get("remember_input_class", ""),
        "autoshow":              bool(p.get("autoshow", False)),
    }
    return ctx
