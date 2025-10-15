"""Template filter to safely access mapping keys without raising errors."""
from __future__ import annotations

from typing import Any

from django import template

register = template.Library()


@register.filter(name="safeget")
def safeget(mapping: Any, key: str) -> Any:
    """Return mapping[key] without raising if missing.

    Falls back to attribute access and finally returns an empty string.
    """
    if mapping is None or key is None:
        return ""
    try:
        if isinstance(mapping, dict):
            return mapping.get(key, "")
        value = getattr(mapping, key, "")
        return value if value is not None else ""
    except Exception:  # pragma: no cover - defensive
        return ""
