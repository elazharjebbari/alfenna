from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

import yaml
from django.conf import settings

logger = logging.getLogger("atelier.i18n.providers")


class TranslationProvider:
    def get(self, key: str, *, locale: str, site_version: str) -> Optional[str]:
        raise NotImplementedError


class DBTranslationProvider(TranslationProvider):
    """
    Database-backed provider that resolves keys produced by build_translation_key().
    """

    def get(self, key: str, *, locale: str, site_version: str) -> Optional[str]:
        if not isinstance(key, str) or not key.startswith("db:"):
            return None

        from apps.i18n.models import StringTranslation
        from apps.i18n.utils import parse_translation_key, split_field_components

        normalized_locale = (locale or "").strip().lower()
        normalized_site = (site_version or "").strip().lower()

        locale_candidates: list[str] = []
        if normalized_locale:
            locale_candidates.append(normalized_locale)
            if "-" in normalized_locale:
                base = normalized_locale.split("-", 1)[0]
                if base not in locale_candidates:
                    locale_candidates.append(base)
        default_locale = getattr(settings, "ATELIER_I18N_DEFAULT_LOCALE", "fr").lower()
        if default_locale and default_locale not in locale_candidates:
            locale_candidates.append(default_locale)

        model_label_value, object_id, field_path = parse_translation_key(key)
        base_field, suffix, embedded_site = split_field_components(field_path)

        def compose_field(site: Optional[str]) -> str:
            field_name = base_field
            if suffix:
                field_name = f"{field_name}.{suffix}"
            if site and site not in {"", "core"}:
                field_name = f"{field_name}@{site}"
            return field_name

        field_candidates: list[str] = []
        if embedded_site:
            field_candidates.append(compose_field(embedded_site))
        elif normalized_site and normalized_site not in {"", "core"}:
            field_candidates.append(compose_field(normalized_site))
        field_candidates.append(compose_field(None))
        if embedded_site:
            field_candidates.append(compose_field(None))

        field_candidates = list(dict.fromkeys(field_candidates))

        qs = (
            StringTranslation.objects.filter(
                model_label=model_label_value,
                object_id=object_id,
                field__in=field_candidates,
                language__in=locale_candidates,
                status="active",
            )
            .values("field", "language", "text")
        )
        lookup_map: Dict[Tuple[str, str], str] = {}
        for row in qs:
            row_locale = (row["language"] or "").lower()
            row_field = row["field"]
            lookup_map[(row_locale, row_field)] = row["text"]

        ordered_fields: list[str] = []
        if embedded_site:
            ordered_fields.append(compose_field(embedded_site))
        elif normalized_site and normalized_site not in {"", "core"}:
            ordered_fields.append(compose_field(normalized_site))
        ordered_fields.append(compose_field(None))
        ordered_fields = list(dict.fromkeys(ordered_fields))

        for loc in locale_candidates:
            for field_name in ordered_fields:
                candidate = lookup_map.get((loc, field_name))
                if candidate is not None:
                    return candidate

        return None


class YamlCatalogProvider(TranslationProvider):
    """
    YAML-backed provider that looks up keys inside configs/atelier/<namespace>/i18n/<locale>.yml,
    then falls back to the core namespace if the key cannot be resolved.
    """

    _catalog_cache: Dict[Tuple[str, str], Tuple[Optional[Tuple[float, int]], Dict[str, Any]]] = {}
    _value_cache: Dict[Tuple[str, str, str], Optional[str]] = {}

    def __init__(self) -> None:
        base_dir = Path(getattr(settings, "BASE_DIR", Path(__file__).resolve().parents[3]))
        self._root = base_dir / "configs" / "atelier"
        self._default_locale = self._normalize_locale(getattr(settings, "ATELIER_I18N_DEFAULT_LOCALE", "fr"))

    def get(self, key: str, *, locale: str, site_version: str) -> Optional[str]:
        if not isinstance(key, str) or not key.strip():
            return None

        cache_key = (self._normalize_namespace(site_version), self._normalize_locale(locale), key.strip())
        if cache_key in self._value_cache:
            return self._value_cache[cache_key]

        namespace = cache_key[0]
        locale_candidates = self._candidate_locales(cache_key[1])
        resolved: Optional[str] = None
        for loc in locale_candidates:
            # Attempt site namespace first
            resolved = self._lookup(namespace, loc, key)
            if resolved is not None:
                break
            # Fallback to core if needed
            if namespace != "core":
                resolved = self._lookup("core", loc, key)
                if resolved is not None:
                    break

        self._value_cache[cache_key] = resolved
        return resolved

    def _lookup(self, namespace: str, locale: str, key: str) -> Optional[str]:
        catalog = self._load_catalog(namespace, locale)
        if not catalog:
            return None
        return self._lookup_key(catalog, key)

    def _load_catalog(self, namespace: str, locale: str) -> Dict[str, Any]:
        cache_key = (namespace, locale)
        path = self._catalog_path(namespace, locale)
        fingerprint = self._fingerprint(path)

        cached = self._catalog_cache.get(cache_key)
        if cached and cached[0] == fingerprint:
            return cached[1]

        if fingerprint is None:
            catalog: Dict[str, Any] = {}
        else:
            try:
                text = path.read_text(encoding="utf-8")
                data = yaml.safe_load(text) or {}
                catalog = data if isinstance(data, dict) else {}
            except FileNotFoundError:
                catalog = {}
            except Exception:  # pragma: no cover - defensive logging path
                logger.warning("Failed to load catalog namespace=%s locale=%s", namespace, locale, exc_info=True)
                catalog = {}

        self._catalog_cache[cache_key] = (fingerprint, catalog)
        return catalog

    def _catalog_path(self, namespace: str, locale: str) -> Path:
        return self._root / namespace / "i18n" / f"{locale}.yml"

    @staticmethod
    def _fingerprint(path: Path) -> Optional[Tuple[float, int]]:
        try:
            stat = path.stat()
        except FileNotFoundError:
            return None
        return stat.st_mtime, stat.st_size

    @staticmethod
    def _lookup_key(catalog: Mapping[str, Any], dotted: str) -> Optional[str]:
        node: Any = catalog
        for segment in (piece.strip() for piece in dotted.split(".") if piece.strip()):
            if isinstance(node, Mapping) and segment in node:
                node = node[segment]
                continue
            if isinstance(node, list):
                try:
                    index = int(segment)
                except ValueError:
                    return None
                if 0 <= index < len(node):
                    node = node[index]
                    continue
                return None
            return None
        if isinstance(node, (str, int, float)):
            return str(node)
        return None

    def _candidate_locales(self, locale: str) -> Iterable[str]:
        normalized = self._normalize_locale(locale)
        yielded = set()

        if normalized:
            yielded.add(normalized)
            yield normalized
            if "-" in normalized:
                base = normalized.split("-", 1)[0]
                base_norm = self._normalize_locale(base)
                if base_norm and base_norm not in yielded:
                    yielded.add(base_norm)
                    yield base_norm

        if self._default_locale and self._default_locale not in yielded:
            yield self._default_locale

    @staticmethod
    def _normalize_locale(locale: str | None) -> str:
        if not locale:
            return ""
        return str(locale).strip().lower().replace("_", "-")

    @staticmethod
    def _normalize_namespace(namespace: str | None) -> str:
        candidate = (namespace or "").strip()
        return candidate or "core"


class NullDBProvider(TranslationProvider):
    """Placeholder provider for future database-backed translations."""

    def get(self, key: str, *, locale: str, site_version: str) -> Optional[str]:
        return None


__all__ = [
    "TranslationProvider",
    "DBTranslationProvider",
    "YamlCatalogProvider",
    "NullDBProvider",
]
