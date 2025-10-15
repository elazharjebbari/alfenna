"""Safe dictionary access filter."""
from __future__ import annotations

from django import template

register = template.Library()


@register.filter(name="safeget")
def safeget(mapping, key):
    """Return mapping[key] or getattr(mapping, key) without raising errors."""
    if mapping is None or key is None:
        return ""
    try:
        if isinstance(mapping, dict):
            value = mapping.get(key, "")
        else:
            value = getattr(mapping, key, "")
        return "" if value is None else value
    except Exception:  # pragma: no cover - defensive guard
        return ""
