# -*- coding: utf-8 -*-
from uuid import uuid4
from typing import Dict, Any, List

ALLOWED_CHOICE_KEYS = {"persona", "label", "sublabel", "icon"}

def _short_id(prefix: str = "mc-pills") -> str:
    return f"{prefix}-{uuid4().hex[:8]}"

def _sanitize_choices(raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for c in (raw or []):
        out.append({k: (c.get(k) or "") for k in ALLOWED_CHOICE_KEYS})
    # Maximum 3 (règle tunnel)
    return out[:3]

def micro_choice_pills(request, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Construit le contexte du composant 'micro-choice/pills' (manifest-first).
    - Génère un id si absent
    - Whitelist des clés
    - Valeurs par défaut d’événements si non fournis
    - Pré-sélection optionnelle via ?persona=APPR (debug/a-b)
    """
    ctx = dict(params or {})

    # id stable pour l'instance
    ctx["id"] = ctx.get("id") or _short_id()

    # Choices (whitelist & cap à 3)
    ctx["choices"] = _sanitize_choices(ctx.get("choices") or [])

    # Header flags
    ctx["show_header"] = bool(ctx.get("show_header"))

    # A11y
    ctx["aria_label"] = ctx.get("aria_label") or "Je veux"

    # Events
    ev = dict(ctx.get("events") or {})
    ev.setdefault("view", "choice_view")
    ev.setdefault("click", "choice_card_click")
    ctx["events"] = ev

    # Style / options pass-through (manifest-first)
    ctx["style"] = ctx.get("style") or {}
    opt = dict(ctx.get("options") or {})
    # allow debug preselect via URL ?persona=APPR
    pre = (request.GET.get("persona") or "").strip().upper()
    if pre in {"APPR", "VENDRE", "OFFRIR"}:
        # le JS lira depuis localStorage; ici on ne peut pas le poser, on expose juste pour tests
        opt.setdefault("preselect", pre)
    opt.setdefault("anchor_next", "#pack-offres")
    opt.setdefault("autoselect_from_storage", True)
    ctx["options"] = opt

    return ctx
