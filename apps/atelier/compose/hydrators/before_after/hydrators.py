from __future__ import annotations
from typing import Any, Dict, Mapping, List, Optional
import uuid
import logging

logger = logging.getLogger("atelier.before_after.debug")

# ---------- helpers ----------
def _as_dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}

def _as_list_of_dicts(x: Any) -> List[Dict[str, Any]]:
    if not isinstance(x, list):
        return []
    return [it for it in x if isinstance(it, dict)]

def _s(x: Any, default: str = "") -> str:
    return x if isinstance(x, str) else default

def _i(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default

def _b(x: Any, default: bool = False) -> bool:
    if isinstance(x, bool): return x
    if isinstance(x, str): return x.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(x, (int, float)): return bool(x)
    return default

def _brief(val: Any, maxlen: int = 220) -> str:
    try:
        s = repr(val)
    except Exception:
        s = f"<{type(val).__name__}>"
    return s if len(s) <= maxlen else s[:maxlen] + "…"

def _log(phase: str, payload: Mapping[str, Any]):
    logger.warning("BA/WIPE %s :: %s", phase, _brief(payload))

# ---------- hydrator ----------
def wipe(request, params: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Before/After 'A1 — Range minimal (accessibility-first)'
    - 2 images superposées, masque piloté par <input type=range>
    - Fallback robuste mobile + boutons 0/50/100
    - Charte : bg #e7f8ee, handle #309255 par défaut
    """
    p = dict(params or {})
    _log("RAW", p)

    # bloc principal
    title = _s(p.get("title"), "Avant / Après — Résultat concret")
    subtitle = _s(p.get("subtitle"), "")

    before = _as_dict(p.get("before"))
    after  = _as_dict(p.get("after"))

    def normalize_side(side: Dict[str, Any], kind: str) -> Dict[str, Any]:
        # images: passer un *stem* compatible avec {% responsive_picture 'images/foo/bar' %}
        # ex: 'images/before_after/avant-1'
        out = {
            "image": _s(side.get("image"), f"images/before_after/{'avant' if kind=='before' else 'apres'}-1"),
            "alt":   _s(side.get("alt"),   "Bougie - " + ("Avant" if kind=="before" else "Après")),
            "label": _s(side.get("label"), "Avant" if kind=="before" else "Après"),
            "pills": [],
        }
        pills = _as_list_of_dicts(side.get("pills"))
        for it in pills[:3]:  # max 3
            icon = _s(it.get("icon"), "")
            text = _s(it.get("text"), "")
            if icon or text:
                out["pills"].append({"icon": icon, "text": text})
        return out

    before = normalize_side(before, "before")
    after  = normalize_side(after, "after")

    cta_raw = _as_dict(p.get("cta"))
    cta = None
    if cta_raw:
        lab = _s(cta_raw.get("label"), "").strip()
        url = _s(cta_raw.get("url"), "").strip() or "#"
        if lab:
            cta = {"label": lab, "url": url}

    style_raw = _as_dict(p.get("style"))
    style = {
        "bg_color": _s(style_raw.get("bg_color"), "#e7f8ee"),
        "handle_color": _s(style_raw.get("handle_color"), "#309255"),
        "radius": _i(style_raw.get("radius"), 20),
        "shadow": _b(style_raw.get("shadow"), True),
    }

    hint_raw = _as_dict(p.get("hint"))
    hint = {
        "enabled": _b(hint_raw.get("enabled"), True),
        "text": _s(hint_raw.get("text"), "Faites glisser le bouton vert pour comparer l'avant/après."),
        "ok_label": _s(hint_raw.get("ok_label"), "OK"),
        "storage_key": _s(hint_raw.get("storage_key"), ""),
    }
    if not hint["text"].strip():
        hint["enabled"] = False

    options_raw = _as_dict(p.get("options"))
    default_value = min(100, max(0, _i(options_raw.get("default_value"), 50)))
    snap_points = [v for v in [0, 50, 100] if isinstance(v, int)]
    if isinstance(options_raw.get("snap_points"), list):
        tmp = []
        for v in options_raw["snap_points"]:
            try:
                v = int(v)
                if 0 <= v <= 100:
                    tmp.append(v)
            except Exception:
                pass
        if tmp:
            snap_points = tmp

    obj_id = "ba_" + uuid.uuid4().hex[:8]

    ctx = {
        "id": obj_id,
        "title": title,
        "subtitle": subtitle,
        "before": before,
        "after": after,
        "cta": cta,
        "style": style,
        "hint": hint,
        "options": {
            "default_value": default_value,
            "snap_points": snap_points,
        },
        # analytics event names (convention GA4)
        "events": {
            "view": "ba_view",
            "drag": "ba_drag",
            "drag_end": "ba_drag_end",
            "snap_after": "ba_snap_after",
            "kpi_click": "ba_kpi_click",
            "cta_click": "ba_cta_near",
        }
    }
    _log("CTX", ctx)
    return ctx
