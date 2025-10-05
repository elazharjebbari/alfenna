from __future__ import annotations
from typing import Any, Dict, List, Mapping
import uuid
import logging

logger = logging.getLogger("atelier.eco.debug")

# ---------- helpers ----------
def _as_dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}

def _as_list_of_dicts(x: Any) -> List[Dict[str, Any]]:
    if not isinstance(x, list): return []
    return [it for it in x if isinstance(it, dict)]

def _s(x: Any, default: str = "") -> str:
    return x if isinstance(x, str) else default

def _i(x: Any, default: int = 0) -> int:
    try: return int(x)
    except Exception: return default

def _b(x: Any, default: bool = False) -> bool:
    if isinstance(x, bool): return x
    if isinstance(x, str): return x.strip().lower() in {"1","true","yes","on"}
    if isinstance(x, (int, float)): return bool(x)
    return default

def _brief(val: Any, maxlen: int = 220) -> str:
    try: s = repr(val)
    except Exception: s = f"<{type(val).__name__}>"
    return s if len(s) <= maxlen else s[:maxlen] + "…"

def _log(phase: str, payload: Mapping[str, Any]):
    logger.warning("ECO/PROOFS %s :: %s", phase, _brief(payload))

# ---------- hydrator ----------
def eco_proofs(request, params: Mapping[str, Any]) -> Dict[str, Any]:
    """
    'Éco-Proofs' : badges + mini-détails + packshot.
    - Items cliquables (accessible)
    - Micro-hint Driver optionnel (1 seul step)
    - Skin cohérent avec la charte
    """
    p = dict(params or {})
    _log("RAW", p)

    title    = _s(p.get("title"), "Pourquoi naturel = qualité + sécurité")
    subtitle = _s(p.get("subtitle"), "")

    style_raw = _as_dict(p.get("style"))
    style = {
        "bg_color": _s(style_raw.get("bg_color"), "#e7f8ee"),
        "accent":   _s(style_raw.get("accent"),   "#309255"),
        "radius":   _i(style_raw.get("radius"),   20),
        "shadow":   _b(style_raw.get("shadow"),   True),
    }

    image      = _s(p.get("image"), "images/components/eco/packshot.webp")
    image_alt  = _s(p.get("image_alt"), "Bougie + ingrédients naturels")

    # Items (max 6)
    items_in = _as_list_of_dicts(p.get("items"))
    default_items = [
        {"icon":"fa fa-seedling","label":"Cires végétales (soja/colza)","desc":"Sans paraffine ni OGM, traçabilité européenne."},
        {"icon":"fa fa-feather","label":"Mèches 100% coton","desc":"Sans plomb, combustion plus propre."},
        {"icon":"fa fa-vial","label":"Parfums conformes IFRA","desc":"Normes européennes, sans phtalates."},
        {"icon":"fa fa-recycle","label":"Pots réutilisables","desc":"Verre recyclable, zéro déchet."},
    ]
    items = []
    src = items_in if items_in else default_items
    for it in src[:6]:
        items.append({
            "icon":  _s(it.get("icon"), "fa fa-leaf"),
            "label": _s(it.get("label"), "Label"),
            "desc":  _s(it.get("desc"),  ""),
        })

    cta_raw = _as_dict(p.get("cta"))
    cta = None
    if cta_raw:
        lab = _s(cta_raw.get("label"), "").strip()
        url = _s(cta_raw.get("url"), "").strip() or "#"
        if lab: cta = {"label": lab, "url": url}

    opt_raw = _as_dict(p.get("options"))
    start_open = max(0, _i(opt_raw.get("start_open"), 1) - 1)  # 1-based to 0-based
    tour_hint  = _b(opt_raw.get("tour_hint"), True)
    tour_text  = _s(opt_raw.get("tour_text"), "Touchez un badge pour découvrir nos choix écologiques.")

    obj_id = "eco_" + uuid.uuid4().hex[:8]

    ctx = {
        "id": obj_id,
        "title": title,
        "subtitle": subtitle,
        "image": image,
        "image_alt": image_alt,
        "items": items,
        "cta": cta,
        "style": style,
        "options": {
            "start_open": start_open,
            "tour_hint": tour_hint,
            "tour_text": tour_text,
        },
        # analytics
        "events": {
            "view": "eco_view",
            "open": "eco_item_open",
            "cta":  "eco_cta_click",
        }
    }
    _log("CTX", ctx)
    return ctx
