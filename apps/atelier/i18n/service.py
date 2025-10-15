from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

import yaml
from django.conf import settings

log = logging.getLogger("atelier.i18n")

TranslatePlan = Sequence[str]
_CatalogFingerprint = Tuple[float, int]

DEFAULT_NAMESPACE = "core"

_catalog_cache: Dict[Tuple[str, str], Tuple[_CatalogFingerprint | None, Dict[str, Any]]] = {}
_merged_catalog_cache: Dict[
    Tuple[str, str],
    Tuple[Tuple[_CatalogFingerprint | None, _CatalogFingerprint | None], Dict[str, Any]],
] = {}


def _base_dir() -> Path:
    return Path(getattr(settings, "BASE_DIR", Path(__file__).resolve().parents[3]))


def _normalize_locale(locale: str | None) -> str:
    if not locale:
        return ""
    return str(locale).strip().lower().replace("_", "-")


def _normalize_namespace(namespace: str | None) -> str:
    if not namespace:
        return DEFAULT_NAMESPACE
    slug = str(namespace).strip().lower()
    return slug or DEFAULT_NAMESPACE


def _candidate_locales(locale: str | None) -> Iterable[str]:
    normalized = _normalize_locale(locale)
    if normalized:
        yield normalized
        if "-" in normalized:
            base = normalized.split("-")[0]
            if base:
                yield base
    default_locale = _normalize_locale(getattr(settings, "ATELIER_I18N_DEFAULT_LOCALE", "fr"))
    if default_locale:
        yield default_locale


def _catalog_path(namespace: str, locale: str) -> Path:
    return _base_dir() / "configs" / "atelier" / namespace / "i18n" / f"{locale}.yml"


def _fingerprint(path: Path) -> _CatalogFingerprint | None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return (stat.st_mtime, stat.st_size)


def _load_namespace_catalog(
    namespace: str,
    locale: str,
) -> Tuple[_CatalogFingerprint | None, Dict[str, Any]]:
    normalized_namespace = _normalize_namespace(namespace)
    cache_key = (normalized_namespace, locale)
    path = _catalog_path(normalized_namespace, locale)
    fingerprint = _fingerprint(path)

    cached = _catalog_cache.get(cache_key)
    if cached and cached[0] == fingerprint:
        return cached

    if fingerprint is None:
        catalog: Dict[str, Any] = {}
    else:
        try:
            text = path.read_text(encoding="utf-8")
            payload = yaml.safe_load(text) or {}
            catalog = payload if isinstance(payload, dict) else {}
        except Exception:
            log.warning(
                "Failed to load catalog for namespace=%s locale=%s",
                normalized_namespace,
                locale,
                exc_info=True,
            )
            catalog = {}

    cached_value = (fingerprint, catalog)
    _catalog_cache[cache_key] = cached_value
    return cached_value


def _deep_merge_catalogs(base: Mapping[str, Any], override: Mapping[str, Any]) -> Dict[str, Any]:
    if not base and not override:
        return {}
    merged: Dict[str, Any] = {}
    if base:
        merged = copy.deepcopy(dict(base))
    for key, value in (override or {}).items():
        if (
            key in merged
            and isinstance(merged[key], Mapping)
            and isinstance(value, Mapping)
        ):
            merged[key] = _deep_merge_catalogs(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _get_merged_catalog(locale: str, namespace: str | None) -> Dict[str, Any]:
    normalized_locale = (locale or "").strip()
    if not normalized_locale:
        return {}

    site_namespace = _normalize_namespace(namespace)
    base_fp, base_catalog = _load_namespace_catalog(DEFAULT_NAMESPACE, normalized_locale)

    site_fp: _CatalogFingerprint | None = None
    site_catalog: Dict[str, Any] = {}
    if site_namespace != DEFAULT_NAMESPACE:
        site_fp, site_catalog = _load_namespace_catalog(site_namespace, normalized_locale)

    cache_key = (site_namespace, normalized_locale)
    fingerprint_pair = (base_fp, site_fp)
    cached = _merged_catalog_cache.get(cache_key)
    if cached and cached[0] == fingerprint_pair:
        return cached[1]

    merged = _deep_merge_catalogs(base_catalog, site_catalog)
    _merged_catalog_cache[cache_key] = (fingerprint_pair, merged)
    return merged


def load_catalog(locale: str | None, site_version: str | None) -> Dict[str, Any]:
    for candidate in _candidate_locales(locale):
        catalog = _get_merged_catalog(candidate, site_version)
        if catalog:
            return catalog
    return {}


def _lookup_key(catalog: Mapping[str, Any], key: str) -> Any:
    node: Any = catalog
    segments = [segment.strip() for segment in key.split(".") if segment.strip()]

    for segment in segments:
        if isinstance(node, Mapping) and segment in node:
            node = node[segment]
            continue
        if isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
            try:
                index = int(segment)
            except ValueError:
                return None
            if 0 <= index < len(node):
                node = node[index]
                continue
        return None
    return node


def t(
    key: str,
    locale: str | None,
    site_version: str | None,
    default: Any = None,
) -> Any:
    if not isinstance(key, str):
        return default

    for candidate in _candidate_locales(locale):
        catalog = _get_merged_catalog(candidate, site_version)
        if not catalog:
            continue
        resolved = _lookup_key(catalog, key)
        if resolved is not None:
            return resolved

    return default if default is not None else key


def resolve_locale(request) -> str:
    param_locale = None
    try:
        params = getattr(request, "GET", None)
        if params:
            param_locale = params.get("lang")
    except Exception:
        param_locale = None

    if param_locale:
        normalized = _normalize_locale(param_locale)
        if normalized:
            return normalized

    seg_locale = _normalize_locale(getattr(getattr(request, "_segments", None), "lang", None))
    if seg_locale:
        return seg_locale

    request_locale = _normalize_locale(getattr(request, "LANGUAGE_CODE", None))
    if request_locale:
        return request_locale

    site_version = getattr(request, "site_version", None)
    site_map = getattr(settings, "ATELIER_I18N_SITE_MAP", {}) or {}
    if site_version and site_version in site_map:
        mapped = _normalize_locale(site_map.get(site_version))
        if mapped:
            return mapped

    default_locale = _normalize_locale(getattr(settings, "ATELIER_I18N_DEFAULT_LOCALE", "fr"))
    return default_locale or "fr"


def direction(locale: str | None) -> str:
    normalized = _normalize_locale(locale)
    return "rtl" if normalized.startswith("ar") else "ltr"


def _translate_from_catalog_marker(value: str, locale: str | None, site_version: str | None) -> Any:
    key = value[2:].strip()
    if not key:
        return value
    translated = t(key, locale, site_version, default=None)
    if translated is None or translated == key:
        return value
    return translated


def _select_i18n_variant(mapping: Mapping[str, Any], locale: str | None) -> Any:
    normalized_locale = _normalize_locale(locale)

    if normalized_locale and normalized_locale in mapping:
        return mapping[normalized_locale]

    if normalized_locale and "-" in normalized_locale:
        base = normalized_locale.split("-")[0]
        if base in mapping:
            return mapping[base]

    default_locale = _normalize_locale(getattr(settings, "ATELIER_I18N_DEFAULT_LOCALE", "fr"))
    if default_locale and default_locale in mapping:
        return mapping[default_locale]

    if "default" in mapping:
        return mapping["default"]

    for candidate in mapping.values():
        return candidate
    return None


def translate(
    value: Any,
    locale: str | None,
    site_version: str | None,
    *,
    component_id: str | None = None,
) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("t:"):
            return _translate_from_catalog_marker(stripped, locale, site_version)
        return value

    if isinstance(value, Mapping):
        if value.get("_no_i18n"):
            return copy.deepcopy(dict(value))

        raw_mapping = value.get("_i18n")
        if isinstance(raw_mapping, Mapping):
            translated = _select_i18n_variant(raw_mapping, locale)
            if isinstance(translated, Mapping):
                return copy.deepcopy(dict(translated))
            if isinstance(translated, list):
                return [copy.deepcopy(item) for item in translated]

            extras = {k: copy.deepcopy(v) for k, v in value.items() if k != "_i18n"}
            if "value" in extras:
                extras["value"] = translated
                return extras
            if "text" in extras:
                extras["text"] = translated
                return extras
            if extras:
                extras["value"] = translated
                return extras
            return translated

    return value


_STATIC_EXCLUSIONS = frozenset({"_no_i18n", "_i18n", "children", "assets", "html"})


def _parse_plan(plan: TranslatePlan | None) -> List[Tuple[str, ...]]:
    parsed: List[Tuple[str, ...]] = []
    if not plan:
        return parsed
    for entry in plan:
        if not entry:
            continue
        tokens = tuple(segment.strip() for segment in str(entry).split(".") if segment.strip())
        if tokens:
            parsed.append(tokens)
    return parsed


def _match_plan(path: Tuple[str, ...], plan_tokens: Sequence[Tuple[str, ...]]) -> Tuple[str, ...] | None:
    if not plan_tokens:
        return None
    for tokens in plan_tokens:
        if len(tokens) != len(path):
            continue
        for pattern, actual in zip(tokens, path):
            if pattern == "*":
                continue
            if pattern != actual:
                break
        else:
            return tokens
    return None


def _plan_translation_key(component_id: str, path: Tuple[str, ...]) -> str:
    clean_segments = [segment for segment in path if segment]
    joined = ".".join(clean_segments)
    return f"{component_id}.{joined}" if joined else component_id


def _translate_via_plan(
    component_id: str,
    path: Tuple[str, ...],
    value: Any,
    locale: str | None,
    site_version: str | None,
) -> Any:
    if not isinstance(value, str):
        return copy.deepcopy(value)
    lookup_key = _plan_translation_key(component_id, path)
    return t(lookup_key, locale, site_version, default=value)


def _walk(
    value: Any,
    locale: str | None,
    site_version: str | None,
    plan_tokens: Sequence[Tuple[str, ...]],
    path: Tuple[str, ...],
    component_id: str | None,
) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("t:"):
            return _translate_from_catalog_marker(stripped, locale, site_version)
        if component_id and _match_plan(path, plan_tokens):
            return _translate_via_plan(component_id, path, value, locale, site_version)
        translated = t(stripped, locale, site_version)
        if translated != stripped:
            return translated
        return value

    if isinstance(value, Mapping):
        if value.get("_no_i18n"):
            return copy.deepcopy(dict(value))

        if "_i18n" in value and isinstance(value["_i18n"], Mapping):
            return translate(value, locale, site_version)

        result: Dict[str, Any] = {}
        for key, item in value.items():
            key_str = str(key)
            if key_str in _STATIC_EXCLUSIONS:
                result[key_str] = copy.deepcopy(item)
                continue
            result[key_str] = _walk(
                item,
                locale,
                site_version,
                plan_tokens,
                path + (key_str,),
                component_id,
            )
        return result

    if isinstance(value, list):
        output: List[Any] = []
        for index, item in enumerate(value):
            output.append(
                _walk(
                    item,
                    locale,
                    site_version,
                    plan_tokens,
                    path + (str(index),),
                    component_id,
                )
            )
        return output

    if isinstance(value, tuple):
        return tuple(
            _walk(
                item,
                locale,
                site_version,
                plan_tokens,
                path + (str(index),),
                component_id,
            )
            for index, item in enumerate(value)
        )

    if component_id and _match_plan(path, plan_tokens):
        return _translate_via_plan(component_id, path, value, locale, site_version)

    return copy.deepcopy(value)


def i18n_walk(
    data: Any,
    locale: str | None,
    site_version: str | None,
    plan: TranslatePlan | None = None,
    *,
    component_id: str | None = None,
) -> Any:
    plan_tokens = _parse_plan(plan)
    try:
        return _walk(data, locale, site_version, plan_tokens, (), component_id)
    except Exception:
        log.warning("i18n_walk failure locale=%s plan=%s", locale, plan, exc_info=True)
        return data


__all__ = [
    "TranslatePlan",
    "direction",
    "i18n_walk",
    "load_catalog",
    "resolve_locale",
    "t",
    "translate",
]
