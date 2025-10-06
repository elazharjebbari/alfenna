# apps/atelier/compose/hydration.py
from __future__ import annotations
from typing import Any, Dict, Mapping, Optional, List
import logging
from functools import lru_cache

from django.utils.module_loading import import_string

from apps.atelier.components.registry import get as get_component
from apps.atelier.components.registry import NamespaceComponentMissing

log = logging.getLogger("atelier.compose.hydration")


def _is_mapping(v: Any) -> bool:
    return isinstance(v, Mapping)


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Deep-merge prédictible:
      - dict: récursif
      - list/tuple: REPLACE (on ne concatène pas by default)
      - scalaires: override écrase base
    """
    out: Dict[str, Any] = dict(base or {})
    for k, v in (override or {}).items():
        if k in out and isinstance(out[k], Mapping) and isinstance(v, Mapping):
            out[k] = _deep_merge(out[k], v)  # type: ignore[arg-type]
        else:
            out[k] = v
    return out


@lru_cache(maxsize=64)
def _import_callable(dotted_path: str):
    return import_string(dotted_path)


def _call_hydrator(dotted_path: str, request, alias: str, params: dict) -> dict:
    """
    Appelle une fonction Python via import string.
    Signature attendue: func(request, params) -> dict
    """
    try:
        func = _import_callable(dotted_path)
    except Exception as e:
        log.error("Hydration import failed for %s (alias=%s): %s", dotted_path, alias, e)
        return {}
    try:
        res = func(request, params or {})
        if not isinstance(res, dict):
            log.warning("Hydration %s returned non-dict (alias=%s). Ignored.", dotted_path, alias)
            return {}
        return res
    except Exception as e:
        log.exception("Hydration call failed (%s) for alias=%s: %s", dotted_path, alias, e)
        return {}


def _call_many(paths: List[str], request, alias: str, params: dict) -> dict:
    """
    Exécute plusieurs hydrators et merge leurs résultats (ordre déclaré).
    """
    out: dict = {}
    for dotted in paths:
        dotted = (dotted or "").strip()
        if not dotted:
            continue
        ctx = _call_hydrator(dotted, request, alias, params)
        if ctx:
            out = _deep_merge(out, ctx)
    return out


def _hydrate_via_manifest(alias: str, request, merged_params: dict, *, namespace: Optional[str]) -> dict:
    """
    Lecture de la section 'hydrate' issue du registry (alimenté par manifest).
    Supporte:
      - module + func  => module.func(request, params)
      - python | call  => un seul dotted
      - calls: [dotted,...] => chaînage
    Retourne {} si rien à faire; le caller merge avec merged_params.
    """
    comp = get_component(alias, namespace=namespace)
    spec = comp.get("hydrate") or {}
    if not _is_mapping(spec):
        return {}

    # 1) module + func (chemin recommandé)
    module = (spec.get("module") or spec.get("module_path") or "").strip()
    func = (spec.get("func") or spec.get("function") or "").strip()
    if module and func:
        dotted = f"{module}.{func}"
        return _call_hydrator(dotted, request, alias, merged_params)

    # 2) compat: python | call
    single = (spec.get("python") or spec.get("call") or "").strip()
    if single:
        return _call_hydrator(single, request, alias, merged_params)

    # 3) compat: calls: []
    calls = spec.get("calls")
    if isinstance(calls, (list, tuple)):
        paths: List[str] = []
        for it in calls:
            if isinstance(it, str) and it.strip():
                paths.append(it.strip())
        if paths:
            return _call_many(paths, request, alias, merged_params)

    return {}


def load(alias: str, request, params: dict | None = None, *, namespace: Optional[str] = None) -> Dict[str, Any]:
    """
    Variante 1 — Runtime Loader (config-first strict) :
      1) base = manifest.params
      2) merged = deep_merge(base, params_from_page)
      3) ctx_h = hydrator(manifest) si présent, sinon {}
      4) return deep_merge(merged, ctx_h)
    Pas de fallback “magique” vers un module legacy.
    """
    effective_namespace = namespace
    try:
        comp = get_component(alias, namespace=effective_namespace)
    except NamespaceComponentMissing as exc:
        log.error("Hydration called for unknown alias=%s namespace=%s", alias, getattr(exc, "namespace", namespace))
        raise

    base_params = comp.get("params") or {}
    incoming = params or {}
    merged = _deep_merge(base_params, incoming)

    ctx_h = _hydrate_via_manifest(alias, request, merged, namespace=effective_namespace) or {}

    # Hydrateur enrichit/overrides le merged; en cas d'échec on garde merged.
    if not isinstance(ctx_h, dict):
        log.warning("Hydrator for alias=%s returned non-dict; using merged params only.", alias)
        ctx_h = {}

    final_ctx = _deep_merge(merged, ctx_h)
    log.debug("Hydration (manifest-first) alias=%s merged_keys=%s hydr_keys=%s final_keys=%s",
              alias, list(merged.keys()), list(ctx_h.keys()), list(final_ctx.keys()))
    return final_ctx
