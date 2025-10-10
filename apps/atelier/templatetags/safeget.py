from __future__ import annotations

from django import template

register = template.Library()


@register.filter(name="safeget")
def safeget(mapping, key):
    """Safely fetch a key from a mapping; return "" on missing/invalid."""
    if not isinstance(mapping, dict):
        try:
            mapping = dict(mapping or {})
        except Exception:
            return ""
    try:
        value = mapping[key]
    except Exception:
        return ""
    return value
