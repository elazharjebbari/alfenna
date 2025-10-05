from __future__ import annotations
from typing import Optional

from django.core.cache import cache as djcache
from apps.atelier.config.loader import get_cache_defaults, get_cache_slots

"""
Cache de fragments par slot — robuste et déterministe.

- Support TTL par **ID de slot** (p.ex. "hero") ET par **alias composant**
  (p.ex. "header/struct", "footer/main").
- Clamp TTL (>= 1s) pour éviter "expire immédiatement" quand timeout == 0.
- Namespace de clé pour éviter les collisions inter-apps.
"""

_DEFAULTS = get_cache_defaults() or {}
_SLOTS = get_cache_slots() or {}

_DEFAULT_TTL = 600
try:
    _DEFAULT_TTL = int(_DEFAULTS.get("ttl_seconds", _DEFAULT_TTL))
except (TypeError, ValueError):
    _DEFAULT_TTL = 600

_NS = "atelier:frag:"

def _ns(key: str) -> str:
    return f"{_NS}{key}"

def _coerce_int(value, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback

def _raw_ttl_by_key(key: str) -> int:
    ref = _SLOTS.get(key)
    if isinstance(ref, dict) and "ttl_seconds" in ref:
        return _coerce_int(ref["ttl_seconds"], _DEFAULT_TTL)
    return _DEFAULT_TTL

def ttl_for(slot_id: str, alias: str | None = None) -> int:
    ttl = _raw_ttl_by_key(slot_id)
    if ttl == _DEFAULT_TTL and alias:
        ttl = _raw_ttl_by_key(alias)
    return max(1, ttl)

def get_fragment(key: str) -> Optional[str]:
    if not key or not isinstance(key, str):
        return None
    return djcache.get(_ns(key))

def set_fragment(key: str, html: str, ttl_seconds: int | None = None) -> None:
    if not key or not isinstance(key, str):
        return
    if html is None:
        return
    ttl = _coerce_int(ttl_seconds, _DEFAULT_TTL) if ttl_seconds is not None else _DEFAULT_TTL
    ttl = max(1, ttl)
    djcache.set(_ns(key), html, ttl)

def delete_fragment(key: str) -> None:
    if not key or not isinstance(key, str):
        return
    djcache.delete(_ns(key))

def exists(key: str) -> bool:
    if not key or not isinstance(key, str):
        return False
    return djcache.get(_ns(key)) is not None

def build_debug_key(page_id: str, slot_id: str, extra: str = "") -> str:
    parts = [str(page_id or ""), str(slot_id or "")]
    if extra:
        parts.append(str(extra))
    return ":".join(parts)