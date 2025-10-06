# apps/atelier/components/assets.py
from __future__ import annotations

from typing import Dict, List, Iterable, Optional
from django.conf import settings

from apps.atelier.config.loader import FALLBACK_NAMESPACE
from apps.atelier.components.utils import split_alias_namespace

from .registry import get as get_component

# --- Vendors centralisés ------------------------------------------------------
# On peut enrichir au fil de l’eau ; ordre interne des vendors respecté
_VENDORS: Dict[str, Dict[str, List[str]]] = {
    # Exemple : Swiper (utilisé par hero/slider)
    "swiper": {
        "css": ["https://cdn.jsdelivr.net/npm/swiper@11/swiper-bundle.min.css"],
        "js": ["https://cdn.jsdelivr.net/npm/swiper@11/swiper-bundle.min.js"],
        "head": [],
    },
}

def _ensure_list(v) -> List[str]:
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v]
    return [str(v)]

def _normalize_assets_dict(assets: dict | None) -> Dict[str, List[str]]:
    assets = assets or {}
    out = {
        "css": _ensure_list(assets.get("css")),
        "js": _ensure_list(assets.get("js")),
        "head": _ensure_list(assets.get("head")),
    }
    return out

def _expand_vendors(vendors: Iterable[str]) -> Dict[str, List[str]]:
    css: List[str] = []
    js: List[str] = []
    head: List[str] = []
    for v in vendors or []:
        meta = _VENDORS.get(str(v).strip())
        if not meta:
            continue
        css.extend(meta.get("css", []))
        js.extend(meta.get("js", []))
        head.extend(meta.get("head", []))
    return {"css": css, "js": js, "head": head}

def order_and_dedupe(assets: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """
    Déduplication stable (conserve le premier ordre d’apparition).
    """
    out: Dict[str, List[str]] = {}
    for kind in ("css", "js", "head"):
        seen, ordered = set(), []
        for item in assets.get(kind, []):
            s = str(item)
            if s not in seen:
                seen.add(s)
                ordered.append(s)
        out[kind] = ordered
    return out

def collect_for(aliases: List[str], *, namespace: Optional[str] = None) -> Dict[str, List[str]]:
    """
    Collecte les assets pour une liste d’aliases, en insérant d’abord les vendors
    requis par ceux-ci, puis les assets propres à chaque composant, en respectant
    l’ordre des `aliases`.
    """
    all_css: List[str] = []
    all_js: List[str] = []
    all_head: List[str] = []

    # 1) Vendors (par alias, dans l’ordre d’apparition)
    vendor_css: List[str] = []
    vendor_js: List[str] = []
    vendor_head: List[str] = []

    default_ns = namespace or FALLBACK_NAMESPACE
    for alias in aliases or []:
        alias_ns, alias_base = split_alias_namespace(alias, default_ns)
        meta = get_component(alias_base, namespace=alias_ns)
        assets = meta.get("assets") or {}
        vendors = assets.get("vendors") or []
        vmeta = _expand_vendors(vendors)
        vendor_css.extend(vmeta["css"])
        vendor_js.extend(vmeta["js"])
        vendor_head.extend(vmeta["head"])

    # 2) Assets propres aux composants
    for alias in aliases or []:
        alias_ns, alias_base = split_alias_namespace(alias, default_ns)
        meta = get_component(alias_base, namespace=alias_ns)
        assets = _normalize_assets_dict(meta.get("assets"))
        all_css.extend(assets["css"])
        all_js.extend(assets["js"])
        all_head.extend(assets["head"])

    # Vendors d’abord, puis composants
    merged = {
        "css": vendor_css + all_css,
        "js": vendor_js + all_js,
        "head": vendor_head + all_head,
    }
    return order_and_dedupe(merged)

def validate_assets(assets: Dict[str, List[str]], *, strict: bool = False) -> None:
    """
    Validation douce : structure et types. En mode strict (non utilisé par défaut),
    on pourrait vérifier l’existence via staticfiles finders — non requis ici.
    """
    if not isinstance(assets, dict):
        raise TypeError("Assets doivent être un dict {css/js/head: list[str]}.")

    for kind in ("css", "js", "head"):
        val = assets.get(kind, [])
        if not isinstance(val, list):
            raise TypeError(f"Assets['{kind}'] doit être une liste.")
        for s in val:
            if not isinstance(s, str):
                raise TypeError(f"Entrée assets '{kind}' doit être une str, reçu: {type(s)}.")
