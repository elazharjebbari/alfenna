from __future__ import annotations
from typing import Any, Dict, Mapping, List
import logging

logger = logging.getLogger("atelier.usp.debug")

# ---------- helpers ----------
def _as_dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}

def _as_list_of_dicts(x: Any) -> List[Dict[str, Any]]:
    if not isinstance(x, list):
        return []
    return [it for it in x if isinstance(it, dict)]

def _s(x: Any, default: str = "") -> str:
    return x if isinstance(x, str) else default

def _brief(val: Any, maxlen: int = 240) -> str:
    try:
        s = repr(val)
    except Exception:
        s = f"<unrepr {type(val).__name__}>"
    return s if len(s) <= maxlen else s[:maxlen] + "…"

def _log(phase: str, payload: Dict[str, Any], anomalies: List[str], params_keys: List[str]):
    logger.warning("USP %s :: payload=%s anomalies=%s keys=%s",
                   phase, _brief(payload), _brief(anomalies), params_keys)

# ---------- hydrator ----------
def usp_block(request, params: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Normalise le contenu pour le bloc USP (3 variantes visuelles).
    - 4 'pillars' affichés en permanence
    - 2 USP 'contextuelles' selon persona (APPR, VENDRE, OFFRIR)
    - Un segmented-control pour permuter la persona active
    - Pas d'accès externe, 100% config-first
    """
    anomalies: List[str] = []
    p = dict(params or {})
    _log("RAW(usp_block)", p, anomalies, list(p.keys()))

    # Personas
    persona_default = _s(p.get("persona_default"), "APPR").upper()
    personas = []
    for it in _as_list_of_dicts(p.get("personas")):
        code = _s(it.get("code"), "").upper()
        label = _s(it.get("label"), "").strip()
        if code and label:
            personas.append({"code": code, "label": label})
    if not personas:
        personas = [{"code": "APPR", "label": "Apprendre"},
                    {"code": "VENDRE", "label": "Vendre"},
                    {"code": "OFFRIR", "label": "Offrir"}]
    if persona_default not in [x["code"] for x in personas]:
        persona_default = personas[0]["code"]

    # 4 piliers (toujours visibles)
    pillars = []
    for it in _as_list_of_dicts(p.get("pillars"))[:4]:
        icon = _s(it.get("icon"), "")
        title = _s(it.get("title"), "")
        text = _s(it.get("text"), "")
        if title:
            pillars.append({"icon": icon, "title": title, "text": text})
    if not pillars:
        pillars = [
            {"icon": "fas fa-certificate",   "title": "Qualité",    "text": "Méthode claire et reproductible"},
            {"icon": "fas fa-leaf",          "title": "Naturel",    "text": "Cires végétales, zéro paraffine"},
            {"icon": "fas fa-lightbulb",     "title": "Créativité", "text": "Styles, couleurs et finitions"},
            {"icon": "fas fa-hands-helping", "title": "Autonomie",  "text": "Deviens créatrice indépendante"},
        ]

    # USP contextuelles par persona (max 2)
    ctx_map_in = _as_dict(p.get("context"))
    context_by_persona: Dict[str, List[Dict[str, str]]] = {}
    for persona in personas:
        code = persona["code"]
        arr = []
        for it in _as_list_of_dicts(ctx_map_in.get(code)):
            icon = _s(it.get("icon"), "")
            title = _s(it.get("title"), "")
            text = _s(it.get("text"), "")
            if title:
                arr.append({"icon": icon, "title": title, "text": text})
        context_by_persona[code] = arr[:2]

    style_raw = _as_dict(p.get("style"))
    style = { "tone": _s(style_raw.get("tone"), "light") }  # light|soft…

    ctx = {
        "persona_default": persona_default,
        "personas": personas,
        "pillars": pillars,
        "context_by_persona": context_by_persona,
        "style": style,
    }
    _log("NORMALIZED(usp_block)", ctx, anomalies, list(p.keys()))
    return ctx
