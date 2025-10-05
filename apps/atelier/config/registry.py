from __future__ import annotations

from typing import Dict

from .loader import (
    clear_config_cache,
    get_cache_defaults as _gcd,
    get_cache_slots as _gcs,
    get_experiments_spec as _ges,
    get_page_spec as _gps,
    get_qa_policy as _gqa,
    get_vary_fields as _gvf,
    load_config,
)


def refresh_config() -> None:
    """Invalide et recharge la config normalisée pour tous les namespaces."""
    clear_config_cache()


def pages(*, namespace: str | None = None) -> Dict:
    return load_config(namespace).get("pages", {})


def experiments(*, namespace: str | None = None) -> Dict:
    return load_config(namespace).get("experiments", {})


def cache_rules(*, namespace: str | None = None) -> Dict:
    return load_config(namespace).get("cache", {})


def qa_policy(*, namespace: str | None = None) -> Dict:
    return load_config(namespace).get("qa", {})


# shortcuts
get_page_spec = _gps
get_experiments_spec = _ges
get_cache_defaults = _gcd
get_cache_slots = _gcs
get_vary_fields = _gvf
get_qa_policy = _gqa
