from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Iterable, Optional, Tuple

from .providers import DBTranslationProvider, NullDBProvider, TranslationProvider, YamlCatalogProvider


def _normalize_locale(locale: str | None) -> str:
    if not locale:
        return "fr"
    return str(locale).strip().lower().replace("_", "-") or "fr"


def _normalize_site_version(site_version: str | None) -> str:
    candidate = (site_version or "").strip()
    return candidate or "core"


class TranslationService:
    _EXCLUDED_KEYS = {
        "url",
        "href",
        "src",
        "image",
        "img",
        "icon",
        "slug",
        "uuid",
        "id",
        "price",
        "amount",
    }

    def __init__(
        self,
        *,
        locale: str,
        site_version: str,
        providers: Optional[Iterable[TranslationProvider]] = None,
    ) -> None:
        self.locale = _normalize_locale(locale)
        self.site_version = _normalize_site_version(site_version)
        self.providers = list(providers) if providers is not None else [
            _db_provider,
            _yaml_provider,
            _null_provider,
        ]
        self._missing_keys: set[str] = set()
        self._resolved_keys: set[str] = set()

    @property
    def missing_keys(self) -> set[str]:
        return set(self._missing_keys)

    @property
    def resolved_keys(self) -> set[str]:
        return set(self._resolved_keys)

    def t(self, key: str, default: str | None = None) -> str:
        if not isinstance(key, str):
            return default if default is not None else str(key)

        normalized_key = key.strip()
        if not normalized_key:
            return default if default is not None else key

        for provider in self.providers:
            value = provider.get(normalized_key, locale=self.locale, site_version=self.site_version)
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            self._resolved_keys.add(normalized_key)
            return value
        self._missing_keys.add(normalized_key)
        if default is not None:
            return default
        return key

    def walk(self, data: Any, *, path: Tuple[str, ...] = ()) -> Any:
        if isinstance(data, str):
            stripped = data.strip()
            if stripped.startswith("t:"):
                key = stripped[2:].strip()
                if key:
                    return self.t(key, default=data)
                return data
            return data

        if isinstance(data, Mapping):
            if data.get("_no_i18n") is True:
                return {k: v for k, v in data.items() if k != "_no_i18n"}
            # token-only dict: {"t": "..."} optionally with {"default": "..."}
            if set(data.keys()) <= {"t"} or set(data.keys()) <= {"t", "default"}:
                token = data.get("t")
                default_value = data.get("default")
                default_str = default_value if isinstance(default_value, str) else None
                if isinstance(token, str):
                    return self.t(token, default=default_str if default_str is not None else token)
                return default_str if default_str is not None else token

            token = data.get("t")
            if isinstance(token, str):
                fallback = data.get("default")
                fallback_str = fallback if isinstance(fallback, str) else None
                return self.t(token, default=fallback_str if fallback_str is not None else token)

            result: dict[str, Any] = {}
            for key, value in data.items():
                key_str = str(key)
                if key_str.lower() in self._EXCLUDED_KEYS:
                    result[key] = value
                    continue
                result[key] = self.walk(value, path=path + (key_str,))
            return result

        if isinstance(data, list):
            return [self.walk(item, path=path + (str(index),)) for index, item in enumerate(data)]

        if isinstance(data, tuple):
            return tuple(self.walk(item, path=path + (str(index),)) for index, item in enumerate(data))

        return data


_db_provider = DBTranslationProvider()
_yaml_provider = YamlCatalogProvider()
_null_provider = NullDBProvider()

__all__ = ["TranslationService"]
