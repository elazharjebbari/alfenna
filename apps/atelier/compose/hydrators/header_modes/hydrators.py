# apps/atelier/compose/hydrators/header_modes/hydrators.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
import logging

from django.urls import reverse, NoReverseMatch
from django.http import HttpRequest

logger = logging.getLogger("atelier.header.modes")

# ---------- Helpers

def _safe_rev(name: str, kwargs: Optional[dict] = None, default: str = "/") -> str:
    try:
        return reverse(name, kwargs=kwargs or {})
    except NoReverseMatch:
        return default

def _safe_rev_any(names: List[str], kwargs: Optional[dict] = None, default: str = "/") -> str:
    for n in names:
        try:
            return reverse(n, kwargs=kwargs or {})
        except NoReverseMatch:
            continue
    return default

def _mode_from_request(request: HttpRequest, params: dict) -> str:
    override = (params.get("mode_override") or "").strip().lower()
    if override in ("guest", "member"):
        return override
    user = getattr(request, "user", None)
    return "member" if (user and getattr(user, "is_authenticated", False)) else "guest"

def _build_urls(params: dict) -> Dict[str, str]:
    course_slug = (params.get("course_slug") or "bougies-naturelles").strip() or "bougies-naturelles"
    # Pages principales
    home_url    = _safe_rev_any(["pages:home"], default="/")
    packs_url   = _safe_rev_any(["pages:packs"], default="/packs/")
    contact_url = _safe_rev_any(["pages:contact"], default="/contact/")
    login_url   = _safe_rev_any(["pages:login", "login"], default="/login/")
    logout_url  = _safe_rev_any(["accounts:logout"], default="/accounts/logout/")
    # Course detail (on tente plusieurs namespaces puis fallback)
    course_url  = _safe_rev_any(
        ["lecture-stream", "pages:lecture-stream"],
        kwargs={"course_slug": course_slug},
        default=f"/learn/{course_slug}/",
    )
    faq_url = f"{home_url}#faq"   # évite un #faq isolé sur une page sans ancre
    cta_url = f"{packs_url}#packs-offres"

    return {
        "home": home_url, "packs": packs_url, "contact": contact_url,
        "login": login_url, "logout": logout_url, "course": course_url,
        "faq": faq_url, "cta": cta_url,
    }

def _rating_badge_text(params: dict) -> str:
    return (params.get("rating_badge_text") or "★ 4,8 / 5 • 500+").strip()

# ---------- Hydrateurs (STRUCT / MAIN / MOBILE)

def modes_struct(request: HttpRequest, params: dict) -> Dict[str, Any]:
    """
    En-tête structurel (topbar + conteneur enfants).
    Pas d'invention de defaults agressifs : lecture params + normalisation simple.
    """
    topbar = params.get("topbar") or {}
    enabled = bool(topbar.get("enabled", False))
    text_html = topbar.get("text_html") or ""
    deadline_ts = topbar.get("deadline_ts") or ""
    cta = None
    cta_raw = topbar.get("cta") or {}
    if isinstance(cta_raw, dict) and cta_raw.get("label") and cta_raw.get("url"):
        cta = {"label": str(cta_raw["label"]).strip(), "url": str(cta_raw["url"]).strip()}

    return {
        "topbar": {
            "enabled": enabled,
            "text_html": text_html,
            "deadline_ts": deadline_ts,
            **({"cta": cta} if cta else {}),
        }
    }

def modes_main(request: HttpRequest, params: dict) -> Dict[str, Any]:
    mode = _mode_from_request(request, params)
    urls = _build_urls(params)

    # Menus dérivés du mode
    menu_guest = [
        {"label": "Accueil",        "url": urls["home"]},
        {"label": "Nos Offres",     "url": urls["packs"]},
        {"label": "FAQ",            "url": urls["faq"]},
        {"label": "Se connecter",   "url": urls["login"], "icon": "fas fa-user"},
    ]
    menu_member = [
        {"label": "Accueil",            "url": urls["home"]},
        {"label": "Continuer le cours", "url": urls["course"]},
        {"label": "Packs",              "url": urls["packs"]},
        {"label": "Contact",            "url": urls["contact"]},
    ]

    username = ""
    user = getattr(request, "user", None)
    if user and getattr(user, "is_authenticated", False):
        username = getattr(user, "username", "") or getattr(user, "email", "") or ""

    return {
        "mode": mode,
        "menu": menu_member if mode == "member" else menu_guest,
        "primary_cta": {
            "label": (params.get("primary_cta_label") or "Je me lance"),
            "sublabel": (params.get("primary_cta_sublabel") or "Paiement sécurisé • Accès immédiat"),
            "aria": (params.get("primary_cta_aria") or "Je me lance — Accès immédiat"),
            "url": urls["cta"],
        },
        "logo_src": (params.get("logo_src") or "images/logo.webp"),
        "logo_alt": (params.get("logo_alt") or "Lumiere"),
        "home_url": urls["home"],
        "login_url": urls["login"],
        "logout_url": urls["logout"],
        "show_rating_badge": bool(params.get("show_rating_badge", True)),
        "rating_badge_text": _rating_badge_text(params),
        "username": username,
    }

def modes_mobile(request: HttpRequest, params: dict) -> Dict[str, Any]:
    mode = _mode_from_request(request, params)
    urls = _build_urls(params)

    contact = params.get("contact") or {}
    socials = [s for s in (params.get("socials") or []) if isinstance(s, dict) and s.get("url")]

    menu_guest = [
        {"label": "Accueil",        "url": urls["home"]},
        {"label": "Nos Offres",     "url": urls["packs"]},
        {"label": "FAQ",            "url": urls["faq"]},
    ]
    menu_member = [
        {"label": "Accueil",            "url": urls["home"]},
        {"label": "Continuer le cours", "url": urls["course"]},
        {"label": "Packs",              "url": urls["packs"]},
        {"label": "Contact",            "url": urls["contact"]},
    ]

    username = ""
    user = getattr(request, "user", None)
    if user and getattr(user, "is_authenticated", False):
        username = getattr(user, "username", "") or getattr(user, "email", "") or ""

    return {
        "mode": mode,
        "menu": menu_member if mode == "member" else menu_guest,
        "login_url": urls["login"],
        "logout_url": urls["logout"],
        "username": username,
        "contact": {
            "phone_tel": contact.get("phone_tel", ""),
            "phone_display": contact.get("phone_display", ""),
            "email": contact.get("email", ""),
            "address_url": contact.get("address_url", ""),
            "address_text": contact.get("address_text", ""),
        },
        "socials": socials,
    }
