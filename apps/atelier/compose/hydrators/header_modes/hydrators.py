# apps/atelier/compose/hydrators/header_modes/hydrators.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
import logging
import html

from django.urls import reverse, NoReverseMatch
from django.http import HttpRequest
from django.utils import timezone
from django.utils.formats import date_format

logger = logging.getLogger("atelier.header.modes")

# ---------- Helpers

def _norm_icon(raw_icon: dict | None) -> dict | None:
    if not isinstance(raw_icon, dict):
        return None
    kind = str(raw_icon.get("kind") or "").strip().lower()
    value = str(raw_icon.get("value") or "").strip()
    if not kind or not value:
        return None
    if kind not in {"icofont", "flaticon", "fa", "svg"}:
        return None
    icon: Dict[str, str] = {"kind": kind, "value": value}
    color = str(raw_icon.get("color") or "").strip()
    if color:
        icon["color"] = color
    bg = str(raw_icon.get("bg") or "").strip()
    if bg:
        icon["bg"] = bg
    outline = str(raw_icon.get("outline") or "").strip()
    if outline:
        icon["outline"] = outline
    return icon


def _norm_banner(raw_banner: dict | None) -> dict:
    defaults = {
        "enabled": False,
        "colors": {"from": "#2c6a57", "to": "#1f4f42"},
        "speed_ms": 10000,
        "pattern": {
            "url": "images/patterns/alfenna/alfenna_dots_v1.svg",
            "size": 40,
            "opacity": "0.16",
        },
        "messages": [],
    }
    if not isinstance(raw_banner, dict):
        return defaults

    today_local = timezone.localdate()
    today_label = date_format(today_local, "l j F", use_l10n=True)

    messages: List[Dict[str, Any]] = []
    for raw_msg in raw_banner.get("messages", []) or []:
        if not isinstance(raw_msg, dict):
            continue
        text = str(raw_msg.get("text") or "").strip()
        if not text:
            continue
        icon = _norm_icon(raw_msg.get("icon"))
        badge = str(raw_msg.get("badge") or "").strip() or None
        text_escaped = html.escape(text)
        if "[today_human]" in text_escaped:
            text_escaped = text_escaped.replace("[today_human]", f'<span class="af-date">{html.escape(today_label)}</span>')
        messages.append({
            "text": text,
            "text_html": text_escaped,
            "icon": icon,
            "badge": badge,
        })

    colors_raw = raw_banner.get("colors") or {}
    pattern_raw = raw_banner.get("pattern") or {}

    try:
        speed = int(raw_banner.get("speed_ms", defaults["speed_ms"]))
    except (TypeError, ValueError):
        speed = defaults["speed_ms"]
    speed = max(1000, speed)

    try:
        pattern_size = int(pattern_raw.get("size", defaults["pattern"]["size"]))
    except (TypeError, ValueError):
        pattern_size = defaults["pattern"]["size"]
    pattern_size = max(8, pattern_size)

    try:
        pattern_opacity = float(pattern_raw.get("opacity", defaults["pattern"]["opacity"]))
    except (TypeError, ValueError):
        pattern_opacity = defaults["pattern"]["opacity"]
    pattern_opacity = max(0.0, min(pattern_opacity, 1.0))

    opacity_str = f"{pattern_opacity:.4f}".rstrip("0").rstrip(".")

    return {
        "enabled": bool(raw_banner.get("enabled", False)) and bool(messages),
        "colors": {
            "from": str(colors_raw.get("from") or defaults["colors"]["from"]).strip() or defaults["colors"]["from"],
            "to": str(colors_raw.get("to") or defaults["colors"]["to"]).strip() or defaults["colors"]["to"],
        },
        "speed_ms": speed,
        "pattern": {
            "url": str(pattern_raw.get("url") or defaults["pattern"]["url"]).strip() or defaults["pattern"]["url"],
            "size": pattern_size,
            "opacity": opacity_str or "0.16",
        },
        "messages": messages,
    }


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
    # Course detail (on tente plusieurs namespaces puis fallback)
    course_url  = _safe_rev_any(
        ["lecture-stream", "pages:lecture-stream"],
        kwargs={"course_slug": course_slug},
        default=f"/learn/{course_slug}/",
    )
    faq_url = f"{home_url}#faq"   # évite un #faq isolé sur une page sans ancre
    cta_url = f"{packs_url}#packs-offres"

    return {
        "home": home_url,
        "packs": packs_url,
        "contact": contact_url,
        "course": course_url,
        "faq": faq_url,
        "cta": cta_url,
    }


def _default_menu(urls: Dict[str, str]) -> List[Dict[str, str]]:
    return [
        {"label": "Accueil", "url": urls["home"]},
        {"label": "Nos Formations", "url": urls["packs"]},
        {"label": "FAQ", "url": urls["faq"]},
        {"label": "Contact", "url": urls["contact"]},
    ]


def _menu_from_params(raw_menu: Any, urls: Dict[str, str], fallback: List[Dict[str, str]]) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    if isinstance(raw_menu, list):
        for entry in raw_menu:
            if not isinstance(entry, dict):
                continue
            label = str(entry.get("label") or "").strip()
            if not label:
                continue
            url = str(entry.get("url") or "").strip()
            if not url:
                url_name = str(entry.get("url_name") or "").strip()
                if url_name:
                    kwargs_raw = entry.get("url_kwargs") if isinstance(entry.get("url_kwargs"), dict) else {}
                    kwargs_clean = {str(k): v for k, v in (kwargs_raw or {}).items()}
                    url = _safe_rev(url_name, kwargs=kwargs_clean or None, default="")
            if not url:
                key = str(entry.get("key") or "").strip().lower()
                if key:
                    url = urls.get(key, "")
            if not url:
                continue
            icon = str(entry.get("icon") or "").strip()
            item = {"label": label, "url": url}
            if icon:
                item["icon"] = icon
            items.append(item)
    return items or fallback


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
        },
        "banner": _norm_banner(params.get("banner")),
    }

def modes_main(request: HttpRequest, params: dict) -> Dict[str, Any]:
    mode = _mode_from_request(request, params)
    urls = _build_urls(params)

    # Menus dérivés du mode
    default_menu = _default_menu(urls)
    menu_common = _menu_from_params(params.get("menu"), urls, default_menu)

    username = ""
    user = getattr(request, "user", None)
    if user and getattr(user, "is_authenticated", False):
        username = getattr(user, "username", "") or getattr(user, "email", "") or ""

    return {
        "mode": mode,
        "menu": menu_common,
        "primary_cta": {
            "label": (params.get("primary_cta_label") or "Je me lance"),
            "sublabel": (params.get("primary_cta_sublabel") or "Paiement sécurisé • Accès immédiat"),
            "aria": (params.get("primary_cta_aria") or "Je me lance — Accès immédiat"),
            "url": urls["cta"],
        },
        "logo_src": (params.get("logo_src") or "images/logo.webp"),
        "logo_alt": (params.get("logo_alt") or "Lumiere"),
        "home_url": urls["home"],
        "show_rating_badge": bool(params.get("show_rating_badge", True)),
        "rating_badge_text": _rating_badge_text(params),
        "username": username,
    }

def modes_mobile(request: HttpRequest, params: dict) -> Dict[str, Any]:
    mode = _mode_from_request(request, params)
    urls = _build_urls(params)

    contact = params.get("contact") or {}
    socials = [s for s in (params.get("socials") or []) if isinstance(s, dict) and s.get("url")]

    default_menu = _default_menu(urls)
    raw_mobile_menu = params.get("menu_mobile") or params.get("menu")
    menu_common = _menu_from_params(raw_mobile_menu, urls, default_menu)

    username = ""
    user = getattr(request, "user", None)
    if user and getattr(user, "is_authenticated", False):
        username = getattr(user, "username", "") or getattr(user, "email", "") or ""

    return {
        "mode": mode,
        "menu": menu_common,
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
