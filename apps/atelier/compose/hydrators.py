# apps/atelier/compose/hydrators.py.py
from __future__ import annotations
from typing import Dict, Optional

from django.templatetags.static import static
from datetime import datetime

from apps.catalog.models.models import Course

# Réglages Marketing P0
COURSE_SLUG_FOCUS = "initiation-bougies-presentiel"
PROMO_PCT = 30  # affichage marketing


# ================== ENQUÊTE / TRACE HEADER ==================
import logging
from typing import Any, Dict, List
from django.urls import reverse, NoReverseMatch

logger = logging.getLogger("atelier.header.debug")

def _as_dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}

def _as_list_of_dicts(x: Any) -> List[Dict[str, Any]]:
    if not isinstance(x, list):
        return []
    return [it for it in x if isinstance(it, dict)]

def _resolve_url(item: Dict[str, Any]) -> str:
    url = (item.get("url") or "").strip()
    if url:
        return url
    name = (item.get("url_name") or "").strip()
    if not name:
        return "#"
    try:
        kwargs = item.get("url_kwargs") or {}
        return reverse(name, kwargs=kwargs) if kwargs else reverse(name)
    except NoReverseMatch:
        return "#"

def _normalize_menu(menu_in: Any, anomalies: List[str]) -> List[Dict[str, Any]]:
    if isinstance(menu_in, str):
        anomalies.append(f"[menu] attendu=list, reçu=str: {menu_in!r}")
    if not isinstance(menu_in, list):
        return []
    out: List[Dict[str, Any]] = []
    for i, it in enumerate(menu_in):
        if not isinstance(it, dict):
            anomalies.append(f"[menu[{i}]] ignoré: type={type(it).__name__}")
            continue
        label = (it.get("label") or "").strip() or "—"
        rec = {"label": label, "url": _resolve_url(it), "children": []}
        children = it.get("children") or []
        if isinstance(children, list):
            for j, sub in enumerate(children):
                if isinstance(sub, dict):
                    rec["children"].append({
                        "label": (sub.get("label") or "").strip(),
                        "url": _resolve_url(sub),
                    })
                else:
                    anomalies.append(f"[menu[{i}].children[{j}]] ignoré: type={type(sub).__name__}")
        else:
            if children:
                anomalies.append(f"[menu[{i}].children] attendu=list, reçu={type(children).__name__}")
        out.append(rec)
    return out

def _brief(val: Any, maxlen: int = 240) -> str:
    try:
        s = repr(val)
    except Exception:
        s = f"<unrepr: {type(val).__name__}>"
    return s if len(s) <= maxlen else s[:maxlen] + "…"

def _log_phase(phase: str, payload: Dict[str, Any], anomalies: List[str]):
    logger.warning(
        "HEADER %s :: payload=%s  anomalies=%s",
        phase, _brief(payload), _brief(anomalies)
    )

# ------------------ HEADER PARENT ------------------

def header_struct(request, params: Dict[str, Any]) -> Dict[str, Any]:
    anomalies: List[str] = []
    p = params or {}
    _log_phase("RAW(header_struct)", p, anomalies)

    tb_raw = _as_dict(p.get("topbar"))
    if p.get("topbar") and not isinstance(p.get("topbar"), dict):
        anomalies.append(f"[topbar] attendu=dict, reçu={type(p.get('topbar')).__name__}")

    enabled = bool(tb_raw.get("enabled")) if "enabled" in tb_raw else False
    text_html = tb_raw.get("text_html") if isinstance(tb_raw.get("text_html"), str) else ""
    cta_raw = _as_dict(tb_raw.get("cta"))
    cta = None
    if cta_raw:
        label = (cta_raw.get("label") or "").strip()
        url = (cta_raw.get("url") or "").strip()
        if label and url:
            cta = {"label": label, "url": url}
        else:
            anomalies.append("[topbar.cta] label/url manquants")

    contact_raw = _as_dict(p.get("contact"))
    if p.get("contact") and not isinstance(p.get("contact"), dict):
        anomalies.append(f"[contact] attendu=dict, reçu={type(p.get('contact')).__name__}")

    contact = {
        "phone_tel": (contact_raw.get("phone_tel") or "").strip(),
        "phone_display": (contact_raw.get("phone_display") or "").strip(),
        "email": (contact_raw.get("email") or "").strip(),
        "address_url": (contact_raw.get("address_url") or "").strip(),
        "address_text": (contact_raw.get("address_text") or "").strip(),
    }

    socials = []
    s_in = p.get("socials")
    if isinstance(s_in, str):
        anomalies.append(f"[socials] attendu=list, reçu=str: {s_in!r}")
    for s in _as_list_of_dicts(s_in):
        icon = (s.get("icon") or "").strip()
        url = (s.get("url") or "").strip()
        if url:
            socials.append({"icon": icon, "url": url, "new_tab": bool(s.get("new_tab", True))})
        else:
            anomalies.append("[socials] entrée ignorée (url manquante)")

    ctx = {
        "topbar": {"enabled": enabled, "text_html": text_html, "cta": cta},
        "contact": contact,
        "socials": socials,
        "debug_header": {"anomalies": anomalies, "received_keys": list(p.keys())},
    }
    _log_phase("NORMALIZED(header_struct)", ctx, anomalies)
    return ctx

# ------------------ HEADER MAIN (desktop) ------------------

def header_main(request, params: Dict[str, Any]) -> Dict[str, Any]:
    anomalies: List[str] = []
    p = params or {}
    _log_phase("RAW(header_main)", p, anomalies)

    menu = _normalize_menu(p.get("menu"), anomalies)
    show_auth = bool(p.get("show_auth_links", True))

    try:
        home_url = reverse("pages:home")
    except Exception:
        home_url = "/"

    ctx = {
        "logo_src": (p.get("logo_src") or "images/logo.webp"),
        "logo_alt": (p.get("logo_alt") or "Lumière Academy"),
        "menu": menu,
        "show_auth_links": show_auth,
        "home_url": home_url,
        "debug_header": {"anomalies": anomalies, "received_keys": list(p.keys())},
    }
    _log_phase("NORMALIZED(header_main)", ctx, anomalies)
    return ctx

# ------------------ HEADER MOBILE ------------------

def header_mobile(request, params: Dict[str, Any]) -> Dict[str, Any]:
    anomalies: List[str] = []
    p = params or {}
    _log_phase("RAW(header_mobile)", p, anomalies)

    contact_raw = _as_dict(p.get("contact"))
    if p.get("contact") and not isinstance(p.get("contact"), dict):
        anomalies.append(f"[contact] attendu=dict, reçu={type(p.get('contact')).__name__}")

    socials_raw = p.get("socials")
    if isinstance(socials_raw, str):
        anomalies.append(f"[socials] attendu=list, reçu=str: {socials_raw!r}")
    socials = [
        {"icon": (s.get("icon") or "").strip(),
         "url": (s.get("url") or "").strip(),
         "new_tab": bool(s.get("new_tab", True))}
        for s in _as_list_of_dicts(socials_raw)
        if (s.get("url") or "").strip()
    ]

    menu = _normalize_menu(p.get("menu"), anomalies)

    def _safe_rev(name: str, default: str) -> str:
        try:
            return reverse(name)
        except Exception:
            return default

    login_url = p.get("login_url") or _safe_rev("login", "/login/")
    register_url = p.get("register_url") or _safe_rev("register", "/register/")

    ctx = {
        "contact": {
            "phone_tel": (contact_raw.get("phone_tel") or "").strip(),
            "phone_display": (contact_raw.get("phone_display") or "").strip(),
            "email": (contact_raw.get("email") or "").strip(),
            "address_url": (contact_raw.get("address_url") or "").strip(),
            "address_text": (contact_raw.get("address_text") or "").strip(),
        },
        "socials": socials,
        "menu": menu,
        "login_url": login_url,
        "register_url": register_url,
        "debug_header": {"anomalies": anomalies, "received_keys": list(p.keys())},
    }
    _log_phase("NORMALIZED(header_mobile)", ctx, anomalies)
    return ctx
# ================== /TRACE HEADER ==================

def hero_cover(request, params: Dict[str, Any]) -> Dict[str, Any]:
    p = params or {}
    # cast int sûrs
    def _as_int(val, dflt):
        try: return int(val)
        except Exception: return dflt

    price = _as_int(p.get("price", 169), 169)
    promo = _as_int(p.get("promotion_pct", 0), 0)

    rating_raw = _as_dict(p.get("rating"))
    style_raw  = _as_dict(p.get("style"))

    rating = {
        "value": rating_raw.get("value", 4.8),
        "count": rating_raw.get("count", 86000),
    }
    style = {"price_box_bg": style_raw.get("price_box_bg", "#FF4500")}

    return {
        "badge_html": p.get("badge_html") or "",
        "title_sub": p.get("title_sub"),
        "title_main": p.get("title_main"),
        "description": p.get("description"),
        "price": price,
        "promotion_pct": promo,
        "cta": _as_dict(p.get("cta")) or {"label": "Apprenez maintenant", "url": "#"},
        "slider_image": p.get("slider_image") or "images/slider/slider-1",
        "video_url": p.get("video_url") or "https://www.youtube.com/watch?v=Aj75R0ojBa0",
        "rating": rating,
        "style": style,
    }

def training_content(request, params: Dict[str, Any]) -> Dict[str, Any]:
    p = params or {}

    def _as_int(val, dflt):
        try: return int(val)
        except Exception: return dflt

    intro_banner = _as_dict(p.get("intro_banner"))
    if "enabled" not in intro_banner:
        intro_banner["enabled"] = False
    if not isinstance(intro_banner.get("text_html"), str):
        intro_banner["text_html"] = ""

    return {
        "title": p.get("title"),
        "title_suffix": p.get("title_suffix"),
        "subtitle": p.get("subtitle"),
        "image_src": p.get("image_src"),
        "image_alt": p.get("image_alt") or "Bougie artisanale",
        "price": p.get("price"),
        "videos_count": _as_int(p.get("videos_count", 30), 30),
        "modules_count": _as_int(p.get("modules_count", 4), 4),
        "bullets": _as_list_of_dicts(p.get("bullets")) or list(p.get("bullets") or []),
        "bundle_items": list(p.get("bundle_items") or []),
        "bundle_title": p.get("bundle_title") or "Ce que comprend votre pack :",
        "intro_banner": intro_banner,
        "cta": _as_dict(p.get("cta")),
    }

#################################################################################################

# ---------- Helpers internes ----------
def _course_cover_url(course: Course) -> str:
    img = getattr(course, "image", None)
    try:
        if img and hasattr(img, "url") and img.url:
            return img.url
    except Exception:
        pass
    return static("images/placeholders/course_cover.png")


def _serialize_course_min(course: Course) -> dict:
    return {"id": course.id, "title": course.title, "slug": course.slug}


def _serialize_course_card(course: Course) -> dict:
    return {
        "id": course.id,
        "title": course.title,
        "slug": course.slug,
        "cover_url": _course_cover_url(course),
        "difficulty": "Tous niveaux",
        "duration_minutes": None,
        "published_at": course.published_at,
    }


def _get_focus_course() -> Optional[Course]:
    course = (
        Course.objects.filter(slug=COURSE_SLUG_FOCUS, is_published=True)
        .only("id", "title", "slug")
        .first()
    )
    if course:
        return course
    return Course.objects.published().only("id", "title", "slug").first()

def _as_bool(x: Any) -> bool:
    return bool(x) is True

def _base_hero_context() -> dict:
    course = _get_focus_course()
    cdict = _serialize_course_min(course) if course else None
    base = {"course": cdict, "promotion_pct": PROMO_PCT}
    if cdict:
        base["cta"] = {
            "label": "Découvrir le programme",
            "url": f"/courses/{cdict['slug']}/",
            "tracking_id": "hero_cta_primary",
        }
    return base


def hero_slider(request, params: dict) -> Dict[str, Any]:
    base = _base_hero_context()
    base["slides"] = []  # P0: images statiques dans le template
    return base


def _int_or(val: Any, fallback: int) -> int:
    try:
        return int(val)
    except Exception:
        return fallback


def course_list(request, params: dict) -> Dict[str, Any]:
    items = []
    for c in (
        Course.objects.published()
        .only("id", "title", "slug", "image", "published_at")[:12]
    ):
        items.append(_serialize_course_card(c))
    return {"courses": items}


def video_presentation(request, params: dict) -> Dict[str, Any]:
    return {
        "video_sources": [
            {"path": "/media/videos/landingpage/VID_LANDINGPAGE_480p.mp4", "label": "480p"},
            {"path": "/media/videos/landingpage/VID_LANDINGPAGE_720p.mp4", "label": "720p"},
            {"path": "/media/videos/landingpage/VID_LANDINGPAGE_1080p.mp4", "label": "1080p"},
        ],
        "poster_url": "/static/images/formateurs/formatrice_souheila.png",
        "tracking_id": "hero_video",
    }

def _as_int(val: Any, dflt: int) -> int:
    try:
        return int(val)
    except Exception:
        return dflt

def training_detail_formation(request, params: Dict[str, Any]) -> Dict[str, Any]:
    p = params or {}
    return {
        "title_html": p.get("title_html") or "<span>Créez</span> et <span>Vendez</span> Vos Bougies",
        "subtitle": p.get("subtitle") or "",
        "image_src": p.get("image_src") or "images/candles/pot-bougie-detail-formation",
        "image_alt": p.get("image_alt") or "Bougie artisanale",
        "price": _as_int(p.get("price", 179), 179),
        "features": list(p.get("features") or []),
        "bundle_items": list(p.get("bundle_items") or []),
        "cta": p.get("cta") or {"label": "Je Participe", "url": "#"},
    }


def cover_highlights(request, params: Dict[str, Any]) -> Dict[str, Any]:
    p = params or {}
    cards = [c for c in (p.get("cards") or []) if isinstance(c, dict)]
    return {
        "title_html": p.get("title_html") or "Transformez Votre Passion en <span>Compétences Artisanales</span>",
        "subtitle": p.get("subtitle") or "Profitez d'Opportunités Artisanales Inédites",
        "cards": cards,
    }


def faq_main(request, params: Dict[str, Any]) -> Dict[str, Any]:
    p = params or {}
    tabs = [t for t in (p.get("tabs") or []) if isinstance(t, dict)]
    idx = p.get("initial_tab_index", 0)
    try:
        idx = int(idx)
    except Exception:
        idx = 0
    if idx < 0: idx = 0
    if tabs and idx >= len(tabs): idx = 0
    return {"tabs": tabs, "initial_tab_index": idx}


def teacher_presentation(request, params: Dict[str, Any]) -> Dict[str, Any]:
    photo_url = params.get("photo_url") or static("images/formateurs/formatrice_souheila.png")
    return {
        "photo_url": photo_url,
        "intro_html": params.get("intro_html", ""),
        "body_html": params.get("body_html", ""),
    }


def footer_main(request, params: Dict[str, Any]) -> Dict[str, Any]:
    p = params or {}
    year = p.get("year")
    try:
        year = int(year) if year is not None else datetime.utcnow().year
    except Exception:
        year = datetime.utcnow().year

    def _links(lst):
        return [it for it in (lst or []) if isinstance(it, dict) and it.get("label") and it.get("url")]

    socials = []
    for s in p.get("socials", []):
        if isinstance(s, dict) and s.get("url"):
            socials.append({"icon": (s.get("icon") or "").strip(),
                            "url": (s.get("url") or "").strip(),
                            "new_tab": bool(s.get("new_tab", True))})

    return {
        "address_url": (p.get("address_url") or "").strip(),
        "address_text": (p.get("address_text") or "").strip(),
        "email": (p.get("email") or "").strip(),
        "phone_tel": (p.get("phone_tel") or "").strip(),
        "phone_display": (p.get("phone_display") or "").strip(),
        "opening_hours": (p.get("opening_hours") or "").strip(),
        "socials": socials,
        "links_activities": _links(p.get("links_activities")),
        "links_trainings": _links(p.get("links_trainings")),
        "links_quick": _links(p.get("links_quick")),
        "year": year,
    }

def modals_subscribe(request, params: dict) -> Dict[str, Any]:
    # On accepte override via params
    return {
        "form_kind": params.get("form_kind", "email_ebook"),
        "action_url": params.get("action_url", "/api/leads/collect/"),
    }
