from __future__ import annotations
from typing import Any, Dict, List, Optional
from decimal import Decimal, ROUND_HALF_UP
import logging

logger = logging.getLogger("atelier.pricing.debug")

# ---------- Utils ----------
def _as_dict(x: Any) -> Dict[str, Any]: return x if isinstance(x, dict) else {}
def _as_list(x: Any) -> List[Any]: return x if isinstance(x, list) else []

def _brief(val: Any, maxlen: int = 200) -> str:
    try: s = repr(val)
    except Exception: s = f"<unrepr {type(val).__name__}>"
    return s if len(s) <= maxlen else s[:maxlen] + "…"

def _fmt_euro(cents: Optional[int]) -> Optional[str]:
    if cents is None: return None
    euros = (Decimal(cents) / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    s = f"{euros:,.2f}".replace(",", " ").replace(".", ",")  # 1 234,56
    return s

def _fmt_daily(cents: int, divisor_days: int) -> Optional[str]:
    try:
        per_day = (Decimal(cents) / Decimal(100) / Decimal(divisor_days)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        s = f"{per_day:,.2f}".replace(",", " ").replace(".", ",")
        return s
    except Exception:
        return None

def _split_price_parts(formatted: str, currency: str, show_symbol: bool, thin_gap: bool, decimals_show: bool) -> Dict[str, str]:
    """
    Ex: '249,95' -> {'int':'249','sep':',','cents':'95','curr':'€'}
    Ex: '449,00' + decimals_show=True -> montre ',00'; si False -> pas de cents.
    """
    curr = (currency or "").strip()
    int_part, sep, cents = formatted, "", ""
    if "," in formatted:
        int_part, cents = formatted.split(",", 1)
        sep = "," if decimals_show else ""
        if not decimals_show:
            cents = ""
    return {
        "int": int_part,
        "sep": sep,
        "cents": cents,
        "curr": (("\u202f" if thin_gap else " ") + curr) if (show_symbol and curr) else ""
    }

def _installments_text(cents: int, count: int, mode: str, currency: str, thin_gap: bool) -> str:
    if count <= 1: return ""
    if mode == "nice":
        # montant arrondi à l'euro le plus proche (et réajustement sur la dernière échéance si besoin)
        per = int(round(cents / count / 100.0))  # euros
        return f"{count}\u00D7 {per}{' ' if thin_gap else ' '}{currency}"
    # exact (avec centimes)
    per = (Decimal(cents) / Decimal(count)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    s = f"{per:,.2f}".replace(",", " ").replace(".", ",")
    return f"{count}\u00D7 {s}{r' ' if thin_gap else ' '}{currency}"

def _load_plans_from_db() -> List[Dict[str, Any]]:
    try:
        from apps.marketing.models.models_pricing import PricePlan, BonusFeature
    except Exception as ex:
        logger.info("PRICING hydrator: DB models unavailable (%s). Using fallback plans.", ex)
        return []

    plans_qs = PricePlan.objects.filter(is_active=True).order_by("priority", "display_order", "id")
    out: List[Dict[str, Any]] = []
    for plan in plans_qs:
        features: List[str] = []
        for item in plan.get_features():
            if isinstance(item, dict):
                label = str(item.get("label") or "").strip()
                if label:
                    features.append(label)
            elif item is not None:
                label = str(item).strip()
                if label:
                    features.append(label)
        if not features:
            features = list(
                plan.pricefeature_set.filter(included=True)
                .order_by("sort_order")
                .values_list("label", flat=True)
            )

        raw_breakdown = plan.get_value_breakdown()
        breakdown: List[Dict[str, Any]] = []
        for item in raw_breakdown:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            try:
                amount = int(item.get("amount_cents") or 0)
            except Exception:
                try:
                    amount = int(item.get("amount") or 0)
                except Exception:
                    amount = 0
            breakdown.append({"label": label, "amount_cents": max(0, amount)})
        if not breakdown:
            bonuses = plan.pricebonusitem_set.order_by("sort_order")
            breakdown = [{"label": b.label, "amount_cents": b.amount_cents} for b in bonuses]

        bonus_icons = list(
            plan.bonusfeature_set.filter(is_active=True)
            .order_by("sort_order", "id")
            .values("label", "icon_class")
        )

        cta = {
            "label": plan.cta_label or "",
            "sublabel": plan.cta_sublabel or "",
            "aria": plan.cta_aria or "",
            "data_plan": plan.slug,
        }

        second_cta = None
        if plan.second_cta_label and plan.second_cta_url:
            second_cta = {
                "label": plan.second_cta_label,
                "url": plan.second_cta_url,
                "aria": plan.second_cta_aria or "",
                "data_plan": plan.slug,
            }

        out.append(
            {
                "slug": plan.slug,
                "title": plan.title,
                "price_cents": plan.price_cents,
                "old_price_cents": plan.old_price_cents or None,
                "currency": plan.get_currency(),
                "ribbon_label": plan.ribbon_label or "",
                "is_featured": bool(plan.is_featured),
                "features": features,
                "value_breakdown": breakdown,
                "bonus_icons": bonus_icons,
                "payment_note": plan.payment_note or "",
                "cta": cta,
                "second_cta": second_cta,
            }
        )

    return out

# ---------- Main ----------
def pricing_packs(request, params: Dict[str, Any]) -> Dict[str, Any]:
    p = params or {}
    logger.debug("PRICING RAW :: %s", _brief(p))

    # Layout & presenter options
    layout = _as_dict(p.get("layout"))
    presenter = _as_dict(p.get("price_presenter"))

    show_old = bool(p.get("show_old_price") if "show_old_price" in p else True)
    highlight_slug = (p.get("highlight_plan_slug") or "").strip()
    highlight_slug_norm = highlight_slug.lower()

    small_word = (p.get("small_word_near_price") or "").strip()
    show_symbol = bool(presenter.get("show_currency_symbol", True))
    thin_gap    = bool(presenter.get("currency_symbol_gap", True))
    curr_scale  = float(presenter.get("currency_symbol_scale", 0.75))
    decimals_show = bool(presenter.get("decimals_show", True))

    show_daily = bool(presenter.get("show_daily_approx", True))
    daily_div  = int(presenter.get("daily_approx_divisor", 365))
    daily_pref = (presenter.get("daily_approx_prefix") or "≈").strip()
    daily_suf  = (presenter.get("daily_approx_suffix") or "/jour").strip()

    show_saved_mode = (presenter.get("show_amount_saved") or "auto").strip()  # auto|amount|percent|none
    saved_threshold = int(presenter.get("amount_saved_threshold_cents", 10000))

    show_inst = bool(presenter.get("show_installments", True))
    inst_cnt  = max(1, int(presenter.get("installments_count", 3)))
    inst_mode = (presenter.get("installments_round") or "nice").strip()  # nice|exact

    mobile_align_left = (_as_dict(p.get("layout")).get("mobile_price_align", "left") == "left")
    valuebox_visible  = (_as_dict(p.get("layout")).get("valuebox_mode", "visible") == "visible")

    value_stack_raw = _as_dict(p.get("value_stack"))
    try:
        visible_rows = int(value_stack_raw.get("visible_rows", 4))
    except Exception:
        visible_rows = 4
    visible_rows = max(1, visible_rows)
    sticky_raw = _as_dict(value_stack_raw.get("sticky_mobile"))
    def _coerce_int(val: Any, default: int) -> int:
        try:
            return int(val)
        except Exception:
            return default
    value_stack_cfg = {
        "enabled": bool(value_stack_raw.get("enabled", False)),
        "show_for": (value_stack_raw.get("show_for") or "highlight_only").strip() or "highlight_only",
        "visible_rows": visible_rows,
        "more_label": (value_stack_raw.get("more_label") or "Voir tous les bonus").strip() or "Voir tous les bonus",
        "belt_enabled": bool(value_stack_raw.get("belt_enabled", False)),
        "sticky_mobile": {
            "enabled": bool(sticky_raw.get("enabled", False)),
            "target_slug": (sticky_raw.get("target_slug") or "").strip(),
            "appear_after_px": max(0, _coerce_int(sticky_raw.get("appear_after_px"), 420)),
            "hide_near_footer_px": max(0, _coerce_int(sticky_raw.get("hide_near_footer_px"), 320)),
            "min_width_px": max(0, _coerce_int(sticky_raw.get("min_width_px"), 0)),
            "cta_label": (sticky_raw.get("cta_label") or "").strip(),
        },
    }

    bonus_raw = _as_dict(p.get("bonus_icons"))
    try:
        bonus_visible = int(bonus_raw.get("visible_count", 4))
    except Exception:
        bonus_visible = 4
    bonus_visible = max(0, bonus_visible)
    bonus_cfg = {
        "enabled": bool(bonus_raw.get("enabled", False)),
        "plan_slug": (bonus_raw.get("plan_slug") or "").strip(),
        "title": (bonus_raw.get("title") or "").strip(),
        "subtitle": (bonus_raw.get("subtitle") or "").strip(),
        "visible_count": bonus_visible,
    }
    bonus_plan_slug_norm = bonus_cfg["plan_slug"].strip().lower()

    # Plans: DB → fallback
    db_plans = _load_plans_from_db()
    if db_plans:
        plans = db_plans
    else:
        logger.warning("PRICING hydrator: no active PricePlan found, using fallback data")
        plans = _as_list(p.get("fallback_plans"))

    ui_plans: List[Dict[str, Any]] = []
    for raw in plans:
        if not isinstance(raw, dict): continue

        slug  = (raw.get("slug") or "").strip()
        title = (raw.get("title") or "—").strip()
        currency = (raw.get("currency") or "€").strip() or "€"
        price_cents = int(raw.get("price_cents") or 0)
        old_cents   = int(raw.get("old_price_cents") or 0) or None
        features    = _as_list(raw.get("features"))
        vb_items_in = _as_list(_as_dict(raw).get("value_breakdown"))

        # Value breakdown
        vb_items, vb_total = [], 0
        for it in vb_items_in:
            if not isinstance(it, dict): continue
            label = (it.get("label") or "").strip()
            ac    = int(it.get("amount_cents") or 0)
            vb_total += ac
            vb_items.append({"label": label, "amount": _fmt_euro(ac), "amount_cents": ac})
        if vb_items:
            items_visible = vb_items[:visible_rows]
            items_hidden = vb_items[visible_rows:]
            value_breakdown = {
                "items": vb_items,
                "items_visible": items_visible,
                "items_hidden": items_hidden,
                "has_more": bool(items_hidden),
                "total": _fmt_euro(vb_total),
                "total_cents": vb_total,
            }
        else:
            value_breakdown = None

        # Prix formatés
        price_fmt = _fmt_euro(price_cents) or "0,00"
        old_fmt   = _fmt_euro(old_cents) if (show_old and old_cents) else None
        parts     = _split_price_parts(price_fmt, currency, show_symbol, thin_gap, decimals_show)

        # Economies
        amount_saved_text = ""
        if old_cents and old_cents > price_cents and show_saved_mode != "none":
            diff = old_cents - price_cents
            if show_saved_mode == "amount" or (show_saved_mode == "auto" and price_cents >= saved_threshold):
                amount_saved_text = f"Économisez { _fmt_euro(diff) }{(' ' if thin_gap else ' ')}{currency}"
            else:
                # percent off
                pct = (Decimal(diff) / Decimal(old_cents) * Decimal(100)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
                # 37,4 % -> 37 %
                pct_str = f"{pct:.1f}".replace(".", ",")
                if pct_str.endswith(",0"): pct_str = pct_str[:-2]
                amount_saved_text = f"-{pct_str} %"

        # Daily approx
        daily_text = _fmt_daily(price_cents, daily_div) if (show_daily and price_cents) else None

        # Installments
        installments = None
        if show_inst and inst_cnt > 1 and price_cents > 0:
            installments = {
                "count": inst_cnt,
                "text": _installments_text(price_cents, inst_cnt, inst_mode, currency, thin_gap)
            }

        badge_percent = None
        if old_cents and old_cents > price_cents and price_cents:
            try:
                badge_percent = int(round((old_cents - price_cents) / old_cents * 100))
            except Exception:
                badge_percent = None

        checkout_url = f"/billing/checkout/plan/{slug}/" if slug else "/billing/checkout/"
        cta = _as_dict(raw.get("cta"))
        cta["url"] = checkout_url
        cta.setdefault("data_plan", slug)

        second_cta_raw = _as_dict(raw.get("second_cta")) or None
        if second_cta_raw:
            second_cta_raw.setdefault("data_plan", slug)

        plan_slug_norm = slug.lower()
        plan_bonus_icons = None
        bonus_items_in = _as_list(raw.get("bonus_icons"))
        if bonus_cfg["enabled"] and plan_slug_norm == bonus_plan_slug_norm and bonus_items_in:
            bonus_items: List[Dict[str, str]] = []
            for item in bonus_items_in:
                if not isinstance(item, dict):
                    continue
                label = (item.get("label") or "").strip()
                if not label:
                    continue
                icon_class = (item.get("icon_class") or "").strip()
                bonus_items.append({"label": label, "icon_class": icon_class})
            if bonus_items:
                vis_b = bonus_items[:bonus_visible]
                hid_b = bonus_items[bonus_visible:]
                plan_bonus_icons = {
                    "items": bonus_items,
                    "items_visible": vis_b,
                    "items_hidden": hid_b,
                    "has_more": bool(hid_b),
                }

        is_highlighted = bool(raw.get("is_featured") or (highlight_slug_norm and (plan_slug_norm == highlight_slug_norm)))

        ui_plans.append({
            "slug": slug,
            "title": title,
            "currency": currency,
            "currency_nbsp": ("\u202f" if thin_gap else " ") + currency if show_symbol else "",
            "price_amount_raw": price_cents / 100 if price_cents else 0,
            "price_amount": price_fmt,
            "price_parts": parts,
            "old_price_amount": old_fmt,
            "amount_saved_text": amount_saved_text or "",
            "daily_approx": daily_text or "",
            "daily_prefix": daily_pref,
            "daily_suffix": daily_suf,
            "small_word": small_word or "",
            "features": features,
            "ribbon_label": (raw.get("ribbon_label") or "").strip(),
            "is_featured": bool(raw.get("is_featured") or (highlight_slug_norm and (plan_slug_norm == highlight_slug_norm))),
            "is_highlighted": is_highlighted,
            "value_breakdown": value_breakdown,
            "valuebox_visible": valuebox_visible,
            "payment_note": raw.get("payment_note") or "",
            "cta": cta,
            "second_cta": second_cta_raw,
            "mobile_align_left": bool(mobile_align_left),
            "canonical_checkout_url": checkout_url,
            "installments": installments,
            "badge_percent": badge_percent,
            "bonus_icons": plan_bonus_icons,
        })

    ctx = {
        "heading_html": p.get("heading_html") or "Nos offres",
        "badges": _as_dict(p.get("badges")),
        "cta_default": _as_dict(p.get("cta_default")) or {
            "label": "Je me lance", "url": "#cta-buy",
            "aria": "Je me lance — Accès immédiat",
            "sublabel": "Paiement sécurisé • Accès immédiat"
        },
        "proof": _as_dict(p.get("proof")),
        "plans": ui_plans,
        "show_old_price": show_old,
        "value_stack": value_stack_cfg,
        "bonus_icons": bonus_cfg,
        "small_word_near_price": small_word,
    }
    logger.debug("PRICING NORMALIZED :: %s", _brief(ctx))
    return ctx
