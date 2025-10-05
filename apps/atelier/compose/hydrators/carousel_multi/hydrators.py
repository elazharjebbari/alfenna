from __future__ import annotations
from typing import Any, Dict, List

def _as_bool(v, default=False) -> bool:
    if isinstance(v, bool): return v
    if isinstance(v, str):  return v.lower() in ("1","true","yes","on")
    return default

def _as_num(v, default: float) -> float:
    try: return float(v)
    except Exception: return default

def _coerce_persona(v: Any) -> str:
    if not isinstance(v, str): return "all"
    v = v.strip().lower()
    return v if v in {"learn","sell","gift","all"} else "all"

def mc_carousel(request, params: Dict[str, Any]) -> Dict[str, Any]:
    """Hydrateur 'manifest-first' : normalise options, onboarding et slides."""
    p = dict(params or {})

    # Header
    variant      = p.get("variant") or "social_proof"
    section_key  = p.get("section_key") or variant
    show_header  = _as_bool(p.get("show_header"), True)
    title        = (p.get("title") or "").strip()
    subtitle     = (p.get("subtitle") or "").strip()

    # Persona filters
    persona_filters = []
    for it in p.get("persona_filters") or []:
        if isinstance(it, dict) and it.get("key") and it.get("label"):
            persona_filters.append({"key": it["key"], "label": it["label"]})

    # Options d’affichage
    opt_in = p.get("options") or {}
    options = {
        "items_desktop": int(_as_num(opt_in.get("items_desktop"), 3)),
        "items_tablet":  int(_as_num(opt_in.get("items_tablet"), 2)),
        "items_mobile":  int(_as_num(opt_in.get("items_mobile"), 1)),
        "gap_px":        int(_as_num(opt_in.get("gap_px"), 16)),
    }

    # Onboarding
    ob_in = p.get("onboarding") or {}
    onboarding = {
        "enabled":   _as_bool(ob_in.get("enabled"), True),
        "scope":     (ob_in.get("scope") or "session").strip() or "session",
        "step_title": (ob_in.get("step_title") or "Parcourir les avis").strip(),
        "step_desc":  (ob_in.get("step_desc")  or "Faites défiler horizontalement pour tout voir.").strip(),
    }

    # Slides (normalisation minimale)
    cleaned: List[Dict[str, Any]] = []
    for s in p.get("slides") or []:
        if not isinstance(s, dict): continue
        t = str(s.get("type") or "").strip().lower()
        if t not in {"image","video","audio","quote"}: continue
        out = {"type": t, "persona": _coerce_persona(s.get("persona"))}
        if t == "image":
            out["image_src"] = s.get("image_src") or "https://placehold.co/960x540?text=Image"
            if s.get("alt"): out["alt"] = s["alt"]
            if s.get("badges"): out["badges"] = list(s.get("badges") or [])
            if s.get("caption"): out["caption"] = s["caption"]
        elif t == "video":
            out["video_src"] = s.get("video_src") or ""
            if s.get("poster_src"): out["poster_src"] = s["poster_src"]
            if s.get("caption"): out["caption"] = s["caption"]
        elif t == "audio":
            out["audio_src"] = s.get("audio_src") or ""
            if s.get("poster_src"): out["poster_src"] = s["poster_src"]
            if s.get("caption"): out["caption"] = s["caption"]
        else:  # quote
            if s.get("avatar_src"): out["avatar_src"] = s["avatar_src"]
            if s.get("quote"): out["quote"] = s["quote"]
            if s.get("author"): out["author"] = s["author"]
            if s.get("role"): out["role"] = s["role"]
        cleaned.append(out)

    # Contexte final
    ctx = {
        "variant": variant,
        "section_key": section_key,
        "show_header": show_header,
        "title": title,
        "subtitle": subtitle,
        "persona_filters": persona_filters,
        "options": options,
        "slides": cleaned,
        "onboarding": onboarding,
    }

    # Ces deux valeurs alimentent les data-* pour Driver.js
    ctx["data_step_title"] = onboarding["step_title"]
    ctx["data_step_desc"] = onboarding["step_desc"]
    return ctx
