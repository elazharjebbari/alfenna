from __future__ import annotations

from typing import Any, Dict
import re

from django.utils.safestring import mark_safe


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _digits_only(value: str) -> str:
    return re.sub(r"[^0-9]", "", value or "")


def whatsapp(request, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    params = params or {}

    label = params.get("label") or "fab.whatsapp.label"
    aria_label = params.get("aria_label") or "fab.whatsapp.aria_label"
    icon_mode = (params.get("icon_mode") or "vendor").strip().lower()
    icon_vendor = params.get("icon_vendor") or "icofont-whatsapp"
    icon_svg = params.get("icon_svg") or ""
    phone_tel = params.get("phone_tel") or ""
    offset_bottom = _coerce_int(params.get("offset_bottom"), 18)
    offset_right = _coerce_int(params.get("offset_right"), 16)

    prefill_text = params.get("prefill_text") or ""

    product_slug = ""
    resolver_match = getattr(request, "resolver_match", None)
    if resolver_match and hasattr(resolver_match, "kwargs"):
        kwargs = resolver_match.kwargs or {}
        product_slug = kwargs.get("product_slug") or kwargs.get("slug") or ""

    if not prefill_text and product_slug:
        prefill_text = f"Bonjour, j’ai une question sur le produit: {product_slug}"

    phone_compact = _digits_only(str(phone_tel))

    if icon_mode == "svg" and icon_svg.strip():
        icon_html = mark_safe(icon_svg)
    else:
        icon_html = mark_safe(f'<i class="{icon_vendor}" aria-hidden="true"></i>')

    href_base = "https://wa.me/"
    if phone_compact:
        href_base += phone_compact

    return {
        "label": label,
        "aria_label": aria_label,
        "phone_tel": phone_tel,
        "phone_compact": phone_compact,
        "href_base": href_base,
        "icon_html": icon_html,
        "offset_bottom": offset_bottom,
        "offset_right": offset_right,
        "prefill_text": prefill_text,
    }
