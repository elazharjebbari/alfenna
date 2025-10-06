from __future__ import annotations
from typing import Any, Dict, Mapping, List
import logging
from django.utils import timezone

logger = logging.getLogger("atelier.footer.debug")

# ---------- helpers ----------
def _as_dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}

def _as_list_of_dicts(x: Any) -> List[Dict[str, Any]]:
    if not isinstance(x, list):
        return []
    return [it for it in x if isinstance(it, dict)]

def _str(x: Any, default: str = "") -> str:
    return (x or default) if isinstance(x, str) else default

def _brief(val: Any, maxlen: int = 240) -> str:
    try:
        s = repr(val)
    except Exception:
        s = f"<unrepr {type(val).__name__}>"
    return s if len(s) <= maxlen else s[:maxlen] + "…"

def _log(phase: str, payload: Dict[str, Any], anomalies: List[str], params_keys: List[str]):
    logger.warning("FOOTER %s :: payload=%s anomalies=%s keys=%s",
                   phase, _brief(payload), _brief(anomalies), params_keys)

# ---------- normalizers ----------
def _norm_links(lst: Any, anomalies: List[str], field: str) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for i, it in enumerate(_as_list_of_dicts(lst)):
        label = _str(it.get("label"), "").strip()
        url = _str(it.get("url"), "").strip() or "#"
        if not label:
            anomalies.append(f"[{field}[{i}]] label manquant → ignoré")
            continue
        out.append({"label": label, "url": url})
    return out

def _norm_socials(lst: Any, anomalies: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for i, it in enumerate(_as_list_of_dicts(lst)):
        icon = _str(it.get("icon"), "").strip()
        url = _str(it.get("url"), "").strip()
        if not url:
            anomalies.append(f"[socials[{i}]] url absent → ignoré")
            continue
        out.append({"icon": icon, "url": url, "new_tab": bool(it.get("new_tab", True))})
    return out

# ---------- hydrator ----------
def footer_main(request, params: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Footer manifest-first: normalisation stricte + valeurs par défaut sûres.
    """
    anomalies: List[str] = []
    p = dict(params or {})
    _log("RAW(footer_main)", p, anomalies, list(p.keys()))

    address_url = _str(p.get("address_url"), "")
    address_text = _str(p.get("address_text"), "")
    email = _str(p.get("email"), "")
    phone_tel = _str(p.get("phone_tel"), "")
    phone_display = _str(p.get("phone_display"), "")
    opening_hours = _str(p.get("opening_hours"), "")

    socials = _norm_socials(p.get("socials"), anomalies)
    links_activities = _norm_links(p.get("links_activities"), anomalies, "links_activities")
    links_trainings = _norm_links(p.get("links_trainings"), anomalies, "links_trainings")
    links_quick = _norm_links(p.get("links_quick"), anomalies, "links_quick")

    year_raw = p.get("year")
    try:
        year = int(year_raw)
    except Exception:
        year = 0
    if not year:
        year = timezone.now().year

    ctx = {
        "address_url": address_url,
        "address_text": address_text,
        "email": email,
        "phone_tel": phone_tel,
        "phone_display": phone_display,
        "opening_hours": opening_hours,
        "socials": socials,
        "links_activities": links_activities,
        "links_trainings": links_trainings,
        "links_quick": links_quick,
        "year": year,
    }
    _log("NORMALIZED(footer_main)", ctx, anomalies, list(p.keys()))
    return ctx