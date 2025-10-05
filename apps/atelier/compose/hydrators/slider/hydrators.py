from __future__ import annotations
from typing import Any, Dict, Mapping, List, Optional
import logging

logger = logging.getLogger("atelier.slider.debug")

# ----------------- helpers -----------------
def _as_dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}

def _as_list_of_dicts(x: Any) -> List[Dict[str, Any]]:
    if not isinstance(x, list):
        return []
    return [it for it in x if isinstance(it, dict)]

def _s(x: Any, default: str = "") -> str:
    return x if isinstance(x, str) else default

def _f(x: Any, default: float = 0.0) -> float:
    try:
        if isinstance(x, (int, float)):
            return float(x)
        if isinstance(x, str):
            x = x.replace(" ", "").replace("\xa0", "").replace(",", ".")
            return float(x)
    except Exception:
        pass
    return default

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

def _log(phase: str, payload: Dict[str, Any], anomalies: List[str], params_keys: List[str]):
    logger.warning("SLIDER %s :: payload=%s anomalies=%s keys=%s",
                   phase, _brief(payload), _brief(anomalies), params_keys)

def _fmt_money_eu(amount: float, currency: str = "€") -> str:
    """
    Format monétaire style FR :
    - séparateur décimal = virgule
    - espace insécable avant symbole €
    - 2 décimales
    """
    neg = amount < 0
    amount = abs(amount)
    s = f"{amount:,.2f}"             # "1,234.56"
    s = s.replace(",", " ").replace(".", ",")
    out = f"{'-' if neg else ''}{s}\xa0{currency}"
    return out

def _fmt_cost_per_day(amount: float, currency: str = "€") -> str:
    # "≈ 0,50 €/jour" (avec espace insécable avant €)
    money = _fmt_money_eu(amount, currency)
    return f"≈ {money}\u2009/jour"  # thin space avant /jour

# ----------------- hydrator -----------------
def hero_cover(request, params: Mapping[str, Any]) -> Dict[str, Any]:
    """
    HERO / Slider — normalisation stricte + champs dérivés 'prêts à afficher'
    - 100% config-first
    - Défauts en Euros + charte
    """
    anomalies: List[str] = []
    p = dict(params or {})
    _log("RAW(hero_cover)", p, anomalies, list(p.keys()))

    # ----- Contenu principal
    badge_html      = _s(p.get("badge_html"), "")
    title_sub       = _s(p.get("title_sub"), "")
    title_main      = _s(p.get("title_main"), "")
    description     = _s(p.get("description"), "")

    # ----- Preuve sociale
    rating_raw      = _as_dict(p.get("rating"))
    rating = {
        "value": float(rating_raw.get("value")) if isinstance(rating_raw.get("value"), (int, float)) else 0.0,
        "count": _i(rating_raw.get("count"), 0),
    }
    proof_text      = _s(p.get("proof_text"), "500+ apprenantes")

    # ----- Prix & psychologie du prix
    currency        = _s(p.get("currency"), "€")
    price_current   = _f(p.get("price_current"), 149.95)
    price_before    = _f(p.get("price_before"), 199.00)

    # Coût par jour : fixe (si fourni) ou calculé sur la période
    cost_per_day_in = p.get("cost_per_day")
    cost_period_days= _i(p.get("cost_period_days"), 365)
    if isinstance(cost_per_day_in, (int, float, str)):
        cost_per_day_val = _f(cost_per_day_in, 0.0)
    else:
        cost_per_day_val = (price_current / cost_period_days) if cost_period_days > 0 else 0.0

    discount_pct: Optional[int] = None
    if price_before and price_before > price_current:
        try:
            discount_pct = int(round(100 * (price_before - price_current) / price_before))
        except Exception:
            discount_pct = None

    price = {
        "currency": currency,
        "current": price_current,
        "before": price_before if price_before > 0 else None,
        "current_str": _fmt_money_eu(price_current, currency),
        "before_str": _fmt_money_eu(price_before, currency) if price_before > 0 else "",
        "discount_pct": discount_pct,
        "cost_per_day_str": _fmt_cost_per_day(cost_per_day_val, currency),
        "label_only": _s(p.get("price_label_only"), "Seulement"),
    }

    # ----- CTAs
    cta_raw         = _as_dict(p.get("cta"))
    cta = None
    if cta_raw:
        label = _s(cta_raw.get("label"), "").strip()
        url   = _s(cta_raw.get("url"), "").strip() or "#"
        if label:
            cta = {"label": label, "url": url}

    cta2_raw        = _as_dict(p.get("cta_secondary"))
    cta_secondary = None
    if cta2_raw:
        label2 = _s(cta2_raw.get("label"), "").strip()
        url2   = _s(cta2_raw.get("url"), "").strip() or "#"
        if label2:
            cta_secondary = {"label": label2, "url": url2}

    safety_note         = _s(p.get("safety_note"), "Paiement sécurisé • Accès immédiat")
    micro_progress_html = _s(p.get("micro_progress_html"), "")
    timer_deadline_ts   = _s(p.get("timer_deadline_ts"), "")

    # ----- Médias
    slider_image    = _s(p.get("slider_image"), "images/slider/slider-default.png")
    video_url       = _s(p.get("video_url"), "")

    # ----- Style, layout & options responsive
    style_raw       = _as_dict(p.get("style"))
    style = {
        "price_box_bg": _s(style_raw.get("price_box_bg"), "#309255"),
        "layout": _s(style_raw.get("layout"), "circle"),          # "circle" (desktop pastille) | "ribbon" (inline)
        "mobile_price_mode": _s(style_raw.get("mobile_price_mode"), "strip"),  # "strip" | "circle"
        "show_rating_bubble_desktop": bool(style_raw.get("show_rating_bubble_desktop", True)),
        "show_shapes_desktop": bool(style_raw.get("show_shapes_desktop", True)),
        "show_shapes_mobile": bool(style_raw.get("show_shapes_mobile", False)),
    }

    # ----- Trust badges (garantie / sécurité / accès)
    trust_badges = []
    for tb in _as_list_of_dicts(p.get("trust_badges")):
        icon = _s(tb.get("icon"), "")
        text = _s(tb.get("text"), "")
        if icon or text:
            trust_badges.append({"icon": icon, "text": text})

    # ----- A/B variant (propagation analytics)
    ab_variant = _s(p.get("ab_variant"), "")

    ctx = {
        "badge_html": badge_html,
        "title_sub": title_sub,
        "title_main": title_main,
        "description": description,
        "price": price,
        "cta": cta,
        "cta_secondary": cta_secondary,
        "safety_note": safety_note,
        "micro_progress_html": micro_progress_html,
        "timer_deadline_ts": timer_deadline_ts,
        "slider_image": slider_image,
        "video_url": video_url,
        "rating": rating,
        "proof_text": proof_text,
        "style": style,
        "trust_badges": trust_badges,
        "ab_variant": ab_variant,
    }
    _log("NORMALIZED(hero_cover)", ctx, anomalies, list(p.keys()))
    return ctx
