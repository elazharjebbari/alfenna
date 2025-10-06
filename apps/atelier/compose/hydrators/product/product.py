"""Hydrator for the config-first product component."""
from __future__ import annotations

import base64
import json
import logging
from html import escape
from typing import Any, Dict, Iterable

from django.urls import NoReverseMatch, reverse
from django.utils.translation import get_language

from apps.atelier.components.registry import NamespaceComponentMissing, get as get_component
from apps.atelier.components.utils import split_alias_namespace
from apps.atelier.contracts.product import ProductParams

logger = logging.getLogger(__name__)

_REQUIRED_FORM_KEYS: Iterable[str] = ("fullname", "phone")


def _svg_placeholder(width: int, height: int, text: str, *, bg: str = "#f5f7fa", fg: str = "#94a3b8") -> str:
    label = escape((text or "").strip() or "Img")
    font_size = max(16, min(width, height) // 4)
    svg = (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>"
        f"<rect width='100%' height='100%' fill='{bg}'/>"
        f"<text x='50%' y='50%' fill='{fg}' font-family='sans-serif' font-size='{font_size}' text-anchor='middle'"
        f" dominant-baseline='central'>{label}</text>"
        "</svg>"
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


def _resolve_action_url(raw: str) -> str:
    if not raw:
        return ""
    raw = str(raw)
    try:
        return reverse(raw)
    except NoReverseMatch:
        return raw


def hydrate_product(request, params: Dict[str, Any] | None, *, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Return the rendering context for the product component."""
    cfg = ProductParams.from_dict(params)

    form_cfg = cfg.form
    action_url = _resolve_action_url(form_cfg.action_url)
    sign_url = reverse("leads:sign")

    alias_ns, alias_base = split_alias_namespace(form_cfg.alias)
    form_template = None
    if alias_base:
        try:
            meta = get_component(alias_base, namespace=alias_ns)
            form_template = (meta or {}).get("template")
        except NamespaceComponentMissing:
            logger.warning(
                "Form alias '%s' not registered for namespace '%s'", alias_base, alias_ns
            )

    missing_map_keys = [key for key in _REQUIRED_FORM_KEYS if key not in form_cfg.fields_map]
    if missing_map_keys:
        logger.warning(
            "Product component form mapping incomplete; missing keys: %s", ", ".join(missing_map_keys)
        )

    product = cfg.product
    price = product.price
    promo = product.promo_price
    pricing = {
        "currency": product.currency,
        "price": price,
        "promo_price": promo,
        "has_promo": bool(price and promo and promo < price),
        "savings": (price - promo) if (price and promo and price > promo) else None,
    }

    media_images = [img.as_dict() for img in cfg.media_images]
    if media_images:
        for index, item in enumerate(media_images):
            item.setdefault("index", index)
            item.setdefault("thumb", item.get("thumb") or item.get("src"))
    else:
        title_safe = (cfg.product.name or "Produit").strip() or "Produit"
        media_images = [
            {
                "index": idx,
                "src": _svg_placeholder(960, 720, f"{title_safe} {idx + 1}"),
                "thumb": _svg_placeholder(176, 132, str(idx + 1), bg="#e2e8f0"),
                "alt": title_safe,
            }
            for idx in range(3)
        ]

    media = {
        "lightbox": cfg.media_lightbox,
        "images": media_images,
    }

    language_code = getattr(request, "LANGUAGE_CODE", None) or get_language() or "en"
    lang_prefix = str(language_code).lower()[:2]
    rtl_mode = cfg.rtl if cfg.rtl in {"auto", "on", "off"} else "auto"
    is_rtl = rtl_mode == "on" or (rtl_mode == "auto" and lang_prefix in {"ar", "he", "fa"})

    flow_context = {
        "product_id": product.id,
        "product_name": product.name,
    }
    if getattr(request, "GET", None):
        for key in ("campaign", "source", "utm_source", "utm_medium", "utm_campaign"):
            value = request.GET.get(key)
            if value:
                flow_context[key] = value

    flow_config = {
        "form_kind": "product_lead",
        "endpoint_url": action_url or reverse("leads:collect"),
        "require_idempotency": True,
        "require_signed_token": True,
        "sign_url": sign_url,
        "context": flow_context,
    }

    context_out = {
        "product": {
            "id": product.id,
            "name": product.name,
            "description": product.description,
            "price": price,
            "promo_price": promo,
            "currency": product.currency,
            "badges": [badge.as_dict() for badge in product.badges],
            "highlights": list(product.highlights),
        },
        "pricing": pricing,
        "media": media,
        "options": cfg.options,
        "form": {
            "alias": form_cfg.alias,
            "action_url": action_url,
            "fields_map": form_cfg.fields_map,
            "template": form_template,
            "flow_config_json": json.dumps(flow_config, ensure_ascii=False),
        },
        "tracking": cfg.tracking.as_dict(),
        "rtl_mode": rtl_mode,
        "is_rtl": is_rtl,
        "language_prefix": lang_prefix,
    }

    # Provide decimals as strings for JSON friendliness if needed downstream.
    for key in ("price", "promo_price", "savings"):
        value = context_out["pricing"].get(key)
        if value is not None:
            context_out["pricing"][f"{key}_display"] = f"{value:.2f}"

    return context_out
