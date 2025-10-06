from __future__ import annotations
from typing import Any, Dict, Mapping, List
import logging

logger = logging.getLogger("atelier.trainer.debug")

# -------- helpers --------
def _s(x: Any, default: str = "") -> str:
    return (x or default) if isinstance(x, str) else default

def _brief(val: Any, maxlen: int = 240) -> str:
    try:
        s = repr(val)
    except Exception:
        s = f"<unrepr {type(val).__name__}>"
    return s if len(s) <= maxlen else s[:maxlen] + "…"

def _log(phase: str, payload: Dict[str, Any], anomalies: List[str], keys: List[str]):
    logger.warning("TRAINER %s :: payload=%s anomalies=%s keys=%s",
                   phase, _brief(payload), _brief(anomalies), keys)

# -------- hydrator --------
def trainer_profile(request, params: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Normalise le composant 'trainer/profile' sans toucher au DOM ni aux classes.
    Image en lazy via data-src (comme dans le snippet d'origine).
    """
    anomalies: List[str] = []
    p = dict(params or {})
    _log("RAW(trainer_profile)", p, anomalies, list(p.keys()))

    ctx = {
        "section_title_html": _s(p.get("section_title_html"), "Votre <span>Formatrice</span>"),
        "tab_label": _s(p.get("tab_label"), "La formatrice"),
        "tablist_id": _s(p.get("tablist_id"), "myTab"),
        "tabcontent_id": _s(p.get("tabcontent_id"), "myTabContent"),
        "tab_id": _s(p.get("tab_id"), "home"),
        "tab_button_id": _s(p.get("tab_button_id"), "home-tab"),
        "image_static_path": _s(p.get("image_static_path"), "images/formateurs/formatrice_souheila.png"),
        "image_alt": _s(p.get("image_alt"), "graphique"),
        "intro_title_html": _s(p.get("intro_title_html"), "Je suis votre formatrice !"),
        "paragraph_1_html": _s(p.get("paragraph_1_html"), ""),
        "paragraph_2_html": _s(p.get("paragraph_2_html"), ""),
    }

    _log("NORMALIZED(trainer_profile)", ctx, anomalies, list(p.keys()))
    return ctx
