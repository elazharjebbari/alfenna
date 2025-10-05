"""Hydrator for the config-first product component."""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable

from django.urls import NoReverseMatch, reverse
from django.utils.translation import get_language

from apps.atelier.components.registry import NamespaceComponentMissing, get as get_component
from apps.atelier.components.utils import split_alias_namespace
from apps.atelier.contracts.product import ProductParams

logger = logging.getLogger(__name__)

_REQUIRED_FORM_KEYS: Iterable[str] = ("fullname", "phone")


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
    media = {
        "lightbox": cfg.media_lightbox,
        "images": media_images,
    }

    language_code = getattr(request, "LANGUAGE_CODE", None) or get_language() or "en"
    lang_prefix = str(language_code).lower()[:2]
    rtl_mode = cfg.rtl if cfg.rtl in {"auto", "on", "off"} else "auto"
    is_rtl = rtl_mode == "on" or (rtl_mode == "auto" and lang_prefix in {"ar", "he", "fa"})

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
