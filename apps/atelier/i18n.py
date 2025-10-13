from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml
from django.conf import settings
from django.utils.translation import gettext

_I18N_FILENAME = "i18n.yml"


def _normalize_lang(lang: str | None) -> str:
    if not lang:
        return ""
    return str(lang).strip().lower().replace("_", "-")


@lru_cache(maxsize=32)
def _load_namespace(namespace: str) -> Dict[str, Any]:
    base_dir = Path(settings.BASE_DIR)
    path = base_dir / "configs" / "atelier" / namespace / _I18N_FILENAME
    if not path.exists():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw or {}


def load_messages(namespace: str, lang: str | None) -> Dict[str, Any]:
    data = _load_namespace(namespace or "core")
    if not data:
        return {}

    normalized = _normalize_lang(lang)
    candidates = [
        normalized,
        normalized.split("-")[0] if normalized and "-" in normalized else normalized,
        _normalize_lang(getattr(settings, "LANGUAGE_CODE", "")),
    ]
    for candidate in candidates:
        if candidate and candidate in data and isinstance(data[candidate], dict):
            return data[candidate] or {}

    default_section = data.get("default")
    if isinstance(default_section, dict):
        return default_section

    # Fallback to the first dict-like section
    for value in data.values():
        if isinstance(value, dict):
            return value
    return {}


def tr(namespace: str, lang: str | None, key_or_text: str) -> str:
    if not isinstance(key_or_text, str):
        return key_or_text

    messages = load_messages(namespace, lang)
    if messages:
        node: Any = messages
        parts = key_or_text.split(".")
        for part in parts:
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                node = None
                break
        if isinstance(node, str):
            return node

    return gettext(key_or_text)


def i18n_walk(data: Any, namespace: str, lang: str | None):
    if isinstance(data, dict):
        return {key: i18n_walk(value, namespace, lang) for key, value in data.items()}
    if isinstance(data, list):
        return [i18n_walk(item, namespace, lang) for item in data]
    if isinstance(data, tuple):
        return tuple(i18n_walk(item, namespace, lang) for item in data)
    if isinstance(data, str):
        return tr(namespace, lang, data)
    return data


__all__ = ["load_messages", "tr", "i18n_walk", "_load_namespace"]
