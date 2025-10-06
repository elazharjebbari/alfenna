from __future__ import annotations

from typing import Tuple

from apps.atelier.config.loader import FALLBACK_NAMESPACE, list_namespaces


def split_alias_namespace(raw_alias: str, default_namespace: str = FALLBACK_NAMESPACE) -> Tuple[str, str]:
    """Return (namespace, base_alias) for a possibly namespaced alias string."""
    raw_alias = (raw_alias or "").strip()
    if not raw_alias:
        return default_namespace, ""

    parts = raw_alias.split("/", 1)
    known = set(list_namespaces())
    if len(parts) == 2 and parts[0] in known:
        return parts[0], parts[1]
    return default_namespace, raw_alias
