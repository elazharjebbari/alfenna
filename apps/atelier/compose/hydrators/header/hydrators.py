from __future__ import annotations
from typing import Any, Dict, List
import logging
import html

from django.urls import reverse, NoReverseMatch
from django.utils import timezone
from django.utils.formats import date_format

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
        elif children:
            anomalies.append(f"[menu[{i}].children] attendu=list, reçu={type(children).__name__}")
        out.append(rec)
    return out

def _brief(val: Any, maxlen: int = 240) -> str:
    try:
        s = repr(val)
    except Exception:
        s = f"<unrepr {type(val).__name__}>"
    return s if len(s) <= maxlen else s[:maxlen] + "…"

def _log(phase: str, payload: Dict[str, Any], anomalies: List[str], params_keys: List[str]):
    logger.warning("HEADER %s :: payload=%s anomalies=%s keys=%s",
                   phase, _brief(payload), _brief(anomalies), params_keys)

# ---------- Banner helpers ----------

def _norm_icon(raw_icon: Dict[str, Any] | None) -> Dict[str, str] | None:
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


def _norm_banner(raw_banner: Dict[str, Any] | None) -> Dict[str, Any]:
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

    banner = {
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
    return banner

# ---------- HYDRATORS (normalisation sans inventer de defaults) ----------

def header_struct(request, params: Dict[str, Any]) -> Dict[str, Any]:
    anomalies: List[str] = []
    p = params or {}
    _log("RAW(header_struct)", p, anomalies, list(p.keys()))

    tb_raw = _as_dict(p.get("topbar"))
    enabled = bool(tb_raw.get("enabled")) if "enabled" in tb_raw else False
    text_html = tb_raw.get("text_html") if isinstance(tb_raw.get("text_html"), str) else ""
    deadline_ts = tb_raw.get("deadline_ts") if isinstance(tb_raw.get("deadline_ts"), str) else ""

    cta = None
    cta_raw = _as_dict(tb_raw.get("cta"))
    if cta_raw:
        label = (cta_raw.get("label") or "").strip()
        url = (cta_raw.get("url") or "").strip()
        if label and url:
            cta = {"label": label, "url": url}

    contact_raw = _as_dict(p.get("contact"))
    contact = {
        "phone_tel": (contact_raw.get("phone_tel") or "").strip(),
        "phone_display": (contact_raw.get("phone_display") or "").strip(),
        "email": (contact_raw.get("email") or "").strip(),
        "address_url": (contact_raw.get("address_url") or "").strip(),
        "address_text": (contact_raw.get("address_text") or "").strip(),
    }

    socials = []
    for s in _as_list_of_dicts(p.get("socials")):
        url = (s.get("url") or "").strip()
        if not url:
            continue
        socials.append({
            "icon": (s.get("icon") or "").strip(),
            "url": url,
            "new_tab": bool(s.get("new_tab", True)),
        })

    topbar_ctx = {"enabled": enabled, "text_html": text_html, "deadline_ts": deadline_ts}
    if cta:
        topbar_ctx["cta"] = cta

    ctx = {
        "topbar": topbar_ctx,
        "contact": contact,
        "socials": socials,
        "banner": _norm_banner(p.get("banner")),
    }
    _log("NORMALIZED(header_struct)", ctx, anomalies, list(p.keys()))
    return ctx

def header_main(request, params: Dict[str, Any]) -> Dict[str, Any]:
    anomalies: List[str] = []
    p = params or {}
    _log("RAW(header_main)", p, anomalies, list(p.keys()))

    menu = _normalize_menu(p.get("menu"), anomalies)
    show_auth = bool(p.get("show_auth_links", True))

    try:
        home_url = p.get("home_url") or reverse("pages:home")
    except Exception:
        home_url = "/"

    primary_cta_in = _as_dict(p.get("primary_cta"))
    primary_cta = {
        "label": (primary_cta_in.get("label") or "Je me lance").strip(),
        "url": (primary_cta_in.get("url") or "#cta-buy").strip() or "#cta-buy",
        "sublabel": (primary_cta_in.get("sublabel") or "Paiement sécurisé • Accès immédiat").strip(),
        "aria": (primary_cta_in.get("aria") or "Je me lance — Accès immédiat").strip(),
    }

    ctx = {
        "logo_src": (p.get("logo_src") or ""),
        "logo_alt": (p.get("logo_alt") or ""),
        "menu": menu,
        "show_auth_links": show_auth,
        "home_url": home_url,
        "primary_cta": primary_cta,
    }
    _log("NORMALIZED(header_main)", ctx, anomalies, list(p.keys()))
    return ctx

def header_mobile(request, params: Dict[str, Any]) -> Dict[str, Any]:
    anomalies: List[str] = []
    p = params or {}
    _log("RAW(header_mobile)", p, anomalies, list(p.keys()))

    contact_raw = _as_dict(p.get("contact"))
    contact = {
        "phone_tel": (contact_raw.get("phone_tel") or "").strip(),
        "phone_display": (contact_raw.get("phone_display") or "").strip(),
        "email": (contact_raw.get("email") or "").strip(),
        "address_url": (contact_raw.get("address_url") or "").strip(),
        "address_text": (contact_raw.get("address_text") or "").strip(),
    }

    socials = []
    for s in _as_list_of_dicts(p.get("socials")):
        url = (s.get("url") or "").strip()
        if not url:
            continue
        socials.append({
            "icon": (s.get("icon") or "").strip(),
            "url": url,
            "new_tab": bool(s.get("new_tab", True)),
        })

    menu = _normalize_menu(p.get("menu"), anomalies)

    def _safe_rev(name: str, default: str) -> str:
        try:
            return reverse(name)
        except Exception:
            return default

    login_url = p.get("login_url") or _safe_rev("login", "/login/")
    register_url = p.get("register_url") or _safe_rev("register", "/register/")

    ctx = {
        "contact": contact,
        "socials": socials,
        "menu": menu,
        "login_url": login_url,
        "register_url": register_url,
    }
    _log("NORMALIZED(header_mobile)", ctx, anomalies, list(p.keys()))
    return ctx
