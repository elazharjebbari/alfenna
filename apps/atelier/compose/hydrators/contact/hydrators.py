from __future__ import annotations
from typing import Any, Dict, Mapping

PLACEHOLDER_EMPTY = ""


def _clean_str(value: Any, default: str = PLACEHOLDER_EMPTY) -> str:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned if cleaned else default
    return default


def _normalize_tel(value: Any) -> str:
    tel = _clean_str(value)
    if not tel:
        return PLACEHOLDER_EMPTY
    lower = tel.lower()
    if lower.startswith("tel:"):
        return tel
    sanitized = tel.replace(" ", "").replace("-", "")
    return f"tel:{sanitized}"


def contact_info(request, params: Mapping[str, Any]) -> Dict[str, str]:
    data = dict(params or {})
    ctx = {
        "phone_tel": _normalize_tel(data.get("phone_tel")),
        "phone_display": _clean_str(data.get("phone_display")),
        "phone_title": _clean_str(data.get("phone_title")),
        "email": _clean_str(data.get("email")),
        "email_title": _clean_str(data.get("email_title")),
        "address_url": _clean_str(data.get("address_url")),
        "address_text": _clean_str(data.get("address_text")),
        "address_title": _clean_str(data.get("address_title")),
    }
    return ctx


def contact_map(request, params: Mapping[str, Any]) -> Dict[str, str]:
    data = dict(params or {})
    return {
        "map_embed_url": _clean_str(data.get("map_embed_url")),
    }
