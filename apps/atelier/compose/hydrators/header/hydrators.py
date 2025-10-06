from __future__ import annotations
from typing import Any, Dict, List
import logging
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
