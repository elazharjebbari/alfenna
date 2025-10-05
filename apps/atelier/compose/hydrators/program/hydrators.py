from __future__ import annotations
from typing import Any, Dict, List, Mapping
import uuid

def _as_dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}

def _as_list(x: Any) -> List[Any]:
    return x if isinstance(x, list) else []

def _s(x: Any, d: str = "") -> str:
    return x if isinstance(x, str) else d

def roadmap(request, params: Mapping[str, Any]) -> Dict[str, Any]:
    p = dict(params or {})
    style_raw = _as_dict(p.get("style"))
    style = {
        "bg_color": _s(style_raw.get("bg_color"), "#e7f8ee"),
        "line_color": _s(style_raw.get("line_color"), "#98c9aa"),
        "bullet_color": _s(style_raw.get("bullet_color"), "#309255"),
        "radius": int(style_raw.get("radius") or 20),
    }

    steps_out: List[Dict[str, Any]] = []
    for step in _as_list(p.get("steps")):
        icon = _s(_as_dict(step).get("icon"), "fa fa-check-circle")
        title = _s(step.get("title"), "Étape")
        summary_html = _s(step.get("summary_html"), "")
        bullets = [str(b) for b in _as_list(step.get("bullets"))][:6]
        steps_out.append({
            "icon": icon,
            "title": title,
            "summary_html": summary_html,
            "bullets": bullets,
        })

    if not steps_out:
        # fallback minimal (2 étapes)
        steps_out = [
            {"icon":"fa fa-info-circle","title":"Introduction","summary_html":"Bienvenue.","bullets":[]},
            {"icon":"fa fa-flask","title":"Recettes","summary_html":"3 recettes guidées.","bullets":["Jar 180g","Test chaud/froid"]},
        ]

    cta_raw = _as_dict(p.get("cta"))
    cta = None
    if cta_raw:
        lab = _s(cta_raw.get("label"), "").strip()
        url = _s(cta_raw.get("url"), "").strip() or "#"
        if lab: cta = {"label": lab, "url": url}

    return {
        "id": "rm_" + uuid.uuid4().hex[:8],
        "title": _s(p.get("title"), "Programme — aperçu"),
        "subtitle": _s(p.get("subtitle"), ""),
        "style": style,
        "steps": steps_out,
        "cta": cta,
    }
