# apps/atelier/components/registry.py
from __future__ import annotations
from collections import defaultdict
from typing import Dict, List, Optional, TypedDict, Any, Tuple

from django.conf import settings

from apps.atelier.config.loader import FALLBACK_NAMESPACE, list_namespaces, is_valid_namespace

class ComponentMeta(TypedDict, total=False):
    template: str
    params: dict
    assets: dict
    contract: dict
    hydrate: dict
    render: dict
    compose: dict
    params: dict      # ⬅️ NEW

# Stockage en mémoire du registre par namespace
_COMPONENTS: Dict[str, Dict[str, ComponentMeta]] = defaultdict(dict)


def _empty_assets() -> dict:
    return {"css": [], "js": [], "head": [], "vendors": []}


def _assets_disabled_for(alias: str) -> bool:
    if getattr(settings, "ATELIER_DISABLE_REGISTERED_ASSETS", False):
        return True
    strip = getattr(settings, "ATELIER_STRIP_REGISTRY_ALIASES", ())
    return alias in set(strip)


class InvalidNamespaceError(ValueError):
    """Namespace inconnu ou non autorisé."""


class NamespaceComponentMissing(KeyError):
    """Composant introuvable pour le namespace demandé (ni fallback)."""

    def __init__(self, alias: str, namespace: str):
        super().__init__(alias)
        self.alias = alias
        self.namespace = namespace

    def __str__(self) -> str:  # pragma: no cover - string repr helper
        return f"Component '{self.alias}' missing for namespace '{self.namespace}' (and fallback '{FALLBACK_NAMESPACE}')."


def _normalize_namespace(namespace: Optional[str]) -> str:
    slug = (namespace or "").strip() or FALLBACK_NAMESPACE
    if not is_valid_namespace(slug):
        raise InvalidNamespaceError(f"Namespace inconnu: '{slug}'. Connu: {list_namespaces()}")
    return slug


def _namespace_bucket(namespace: str) -> Dict[str, ComponentMeta]:
    slug = _normalize_namespace(namespace)
    return _COMPONENTS[slug]


# ---------------------------
# API publique du registry
# ---------------------------
def exists(alias: str, *, namespace: Optional[str] = None, include_fallback: bool = True) -> bool:
    try:
        get(alias, namespace=namespace, fallback=include_fallback)
        return True
    except NamespaceComponentMissing:
        return False


def get(
    alias: str,
    *,
    namespace: Optional[str] = None,
    fallback: bool = True,
) -> ComponentMeta:
    slug = _normalize_namespace(namespace)
    search_order: List[str] = [slug]
    if fallback and slug != FALLBACK_NAMESPACE:
        search_order.append(FALLBACK_NAMESPACE)

    for ns in search_order:
        bucket = _COMPONENTS.get(ns, {})
        meta = bucket.get(alias)
        if meta:
            return meta

    raise NamespaceComponentMissing(alias, slug)


def all_aliases() -> List[str]:
    aliases: List[str] = []
    for bucket in _COMPONENTS.values():
        aliases.extend(bucket.keys())
    # stable dedupe
    seen = set()
    ordered: List[str] = []
    for alias in aliases:
        if alias not in seen:
            seen.add(alias)
            ordered.append(alias)
    return ordered


def register(
    alias: str,
    template_path: str,
    *,
    namespace: Optional[str] = None,
    assets: Optional[dict] = None,
    contract: Optional[dict] = None,
    hydrate: Optional[dict] = None,
    render: Optional[dict] = None,
    compose: Optional[dict] = None,
    params: Optional[dict] = None,
) -> None:
    """
    Enregistre un composant (idempotent par alias si override géré à l'appelant).
    """
    bucket = _namespace_bucket(namespace)
    provided_assets = assets or _empty_assets()
    if _assets_disabled_for(alias):
        normalized_assets = _empty_assets()
    else:
        normalized_assets = {
            "css": list(provided_assets.get("css", [])),
            "js": list(provided_assets.get("js", [])),
            "head": list(provided_assets.get("head", [])),
            "vendors": list(provided_assets.get("vendors", [])),
        }

    bucket[alias] = {
        "template": template_path,
        "params": params or {},
        "assets": normalized_assets,
        "contract": contract or {"required": {}, "optional": {}},
        "hydrate": hydrate or {},
        "render": render or {},
        "compose": compose or {},
    }


def bulk_register(items: List[Dict[str, Any]], *, override: bool = False) -> Tuple[int, List[str]]:
    """
    Attendu par item:
      {"alias": str, "template": str,
       "params": dict?, "assets": dict?, "contract": dict?, "hydrate": dict?, "render": dict?, "compose": dict?}
    """
    count = 0
    warnings: List[str] = []

    for item in items:
        alias = item.get("alias")
        template = item.get("template") or item.get("template_path")

        if not alias or not template:
            warnings.append(f"skip invalid item (alias/template missing): {item}")
            continue

        namespace = item.get("namespace")
        try:
            bucket = _namespace_bucket(namespace)
        except InvalidNamespaceError as e:
            warnings.append(str(e))
            continue

        if alias in bucket and not override:
            warnings.append(f"collision for alias '{alias}' in namespace '{_normalize_namespace(namespace)}' (override=False)")
            continue

        register(
            alias,
            template,
            namespace=namespace,
            assets=item.get("assets"),
            contract=item.get("contract"),
            hydrate=item.get("hydrate"),
            render=item.get("render"),
            compose=item.get("compose"),
            params=item.get("params"),
        )
        count += 1

    return count, warnings


# ==========================================================
# Enregistrements "manuels" (ex: vendors/core) — inchangé
# ==========================================================
register(
    "vendors/core",
    template_path="components/core/_blank.html",
    namespace=FALLBACK_NAMESPACE,
    assets={
        "head": [
            '<link rel="preconnect" href="https://fonts.googleapis.com">',
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
            '<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">',
            '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css">',
        ],
        "css": [
            "/static/site/core.css",
            "/static/css/plugins/icofont.min.css",
            "/static/css/plugins/flaticon.css",
            "/static/css/plugins/animate.min.css",
            "/static/css/plugins/swiper-bundle.min.css",
            "/static/css/plugins/magnific-popup.css",
            "/static/css/plugins/nice-select.css",
            "/static/css/plugins/apexcharts.css",
            "/static/css/plugins/jqvmap.min.css",
            "/static/css/style.css",
            # "/static/cookies/tarteaucitron.js-1.25.0/css/tarteaucitron.min.css",
        ],
        "js": [
            "/static/js/vendor/modernizr-3.11.2.min.js",
            "/static/js/vendor/jquery-3.5.1.min.js",
            "/static/js/plugins.js",
            "/static/js/main.js",
            "/static/js/bootstrap.bundle.min.js",
            "/static/site/core.js",
            # "/static/cookies/tarteaucitron.js-1.25.0/tarteaucitron.min.js",
        ],
        "vendors": [],
    },
)
