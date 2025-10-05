from __future__ import annotations
from typing import Any, Dict, List, Mapping, Set
import logging
from django.utils.text import slugify

logger = logging.getLogger("atelier.faq.debug")

# -------- helpers --------
def _as_dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}

def _as_list_of_dicts(x: Any) -> List[Dict[str, Any]]:
    if not isinstance(x, list):
        return []
    return [it for it in x if isinstance(it, dict)]

def _s(x: Any, default: str = "") -> str:
    return (x or default) if isinstance(x, str) else default

def _i(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default

def _brief(val: Any, maxlen: int = 240) -> str:
    try:
        s = repr(val)
    except Exception:
        s = f"<unrepr {type(val).__name__}>"
    return s if len(s) <= maxlen else s[:maxlen] + "…"

def _log(phase: str, payload: Dict[str, Any], anomalies: List[str], keys: List[str]):
    logger.warning("FAQ %s :: payload=%s anomalies=%s keys=%s",
                   phase, _brief(payload), _brief(anomalies), keys)

# -------- normalizers --------
def _ensure_unique_id(base: str, used: Set[str]) -> str:
    sid = slugify(base) or "tab"
    if sid not in used:
        used.add(sid)
        return sid
    i = 2
    while f"{sid}-{i}" in used:
        i += 1
    val = f"{sid}-{i}"
    used.add(val)
    return val

def _norm_faqs(lst: Any, anomalies: List[str], field: str) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for i, it in enumerate(_as_list_of_dicts(lst)):
        q = _s(it.get("question_html")).strip()
        a = _s(it.get("answer_html")).strip()
        if not q or not a:
            anomalies.append(f"[{field}[{i}]] incomplet → ignoré")
            continue
        out.append({"question_html": q, "answer_html": a})
    return out

def _norm_chapters(lst: Any, anomalies: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for i, it in enumerate(_as_list_of_dicts(lst)):
        desc = _s(it.get("desc_html")).strip()
        if not desc:
            anomalies.append(f"[chapters[{i}]] desc_html manquant → ignoré")
            continue
        sub: List[Dict[str, str]] = []
        for j, si in enumerate(_as_list_of_dicts(it.get("subitems"))):
            html = _s(si.get("text_html")).strip()
            if not html:
                anomalies.append(f"[chapters[{i}].subitems[{j}]] vide → ignoré")
                continue
            sub.append({"text_html": html})
        out.append({
            "intro": bool(it.get("intro", False)),
            "mt4": bool(it.get("mt4", False)),
            "border_px": _i(it.get("border_px"), 2),
            "icon": _s(it.get("icon"), "fa fa-circle"),
            "desc_html": desc,
            "subitems": sub,
        })
    return out

def _norm_date_section_items(lst: Any, anomalies: List[str]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for i, it in enumerate(_as_list_of_dicts(lst)):
        html = _s(it.get("text_html")).strip()
        if not html:
            anomalies.append(f"[date_section_items[{i}]] vide → ignoré")
            continue
        out.append({"text_html": html})
    return out

def _norm_details_items(lst: Any, anomalies: List[str]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for i, it in enumerate(_as_list_of_dicts(lst)):
        if it.get("kind") == "price":
            out.append({"kind": "price"})
            continue
        html = _s(it.get("text_html")).strip()
        if not html:
            anomalies.append(f"[details_items[{i}]] vide → ignoré")
            continue
        out.append({"text_html": html})
    return out

# -------- hydrator --------
def faq_main(request, params: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Manifest-first. Conserve EXACTEMENT le DOM, les classes et les styles inline
    fournis dans le bloc d'origine. Génère les onglets + contenus.
    """
    anomalies: List[str] = []
    p = dict(params or {})
    _log("RAW(faq_main)", p, anomalies, list(p.keys()))

    title_html = _s(p.get("title_html"), "Questions & <span>Réponses.</span>")
    padding_top = _s(p.get("padding_top"), "60px")
    padding_bottom = _s(p.get("padding_bottom"), "60px")

    tabs_in = _as_list_of_dicts(p.get("tabs"))
    used_ids: Set[str] = set()
    tabs: List[Dict[str, Any]] = []

    for i, t in enumerate(tabs_in):
        label = _s(t.get("label")).strip() or f"Tab {i+1}"
        icon = _s(t.get("icon"), "fa fa-circle")
        ttype = _s(t.get("type"), "faqs")
        tid = _s(t.get("id")) or label
        tid = _ensure_unique_id(tid, used_ids)

        rec: Dict[str, Any] = {"label": label, "icon": icon, "type": ttype, "id": tid}

        if ttype == "faqs":
            rec["faqs"] = _norm_faqs(t.get("faqs"), anomalies, f"tabs[{i}].faqs")

        elif ttype == "contenu":
            rec["image_static_path"] = _s(t.get("image_static_path"),
                                          "images/e_learning/candles/candle-learning.webp")
            rec["image_alt"] = _s(t.get("image_alt"), "Bougie artisanale")
            rec["bubble_color"] = _s(t.get("bubble_color"), "#4CAF50")
            rec["timeline_line_bg"] = _s(t.get("timeline_line_bg"), "#E7F8EE")
            rec["chapters"] = _norm_chapters(t.get("chapters"), anomalies)

        elif ttype == "modalites":
            rec["line_left"] = _s(t.get("line_left"), "27px")
            rec["line_top"] = _s(t.get("line_top"), "100px")
            rec["line_color"] = _s(t.get("line_color"), "#EDEFF3")
            rec["accent"] = _s(t.get("accent"), "#309255")
            rec["price"] = _i(t.get("price"), 0)
            rec["date_section_items"] = _norm_date_section_items(t.get("date_section_items"), anomalies)
            rec["details_items"] = _norm_details_items(t.get("details_items"), anomalies)
            rec["right_image_static_path"] = _s(t.get("right_image_static_path"),
                                                "images/e_learning/candles/pot-bougie-detail-formation.webp")
            rec["right_image_alt"] = _s(t.get("right_image_alt"), "Bougie artisanale")

        else:
            anomalies.append(f"[tabs[{i}]] type inconnu: {ttype!r} → ignoré")
            continue

        tabs.append(rec)

    ctx = {
        "title_html": title_html,
        "padding_top": padding_top,
        "padding_bottom": padding_bottom,
        "tabs": tabs,
    }
    _log("NORMALIZED(faq_main)", ctx, anomalies, list(p.keys()))
    return ctx
