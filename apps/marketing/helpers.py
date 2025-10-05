# apps/marketing/helpers.py  (seules les lignes marquées # NEW ou # FIX sont nouvelles)

from __future__ import annotations
from urllib.parse import urlparse, urlunparse, urlencode
from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest
from django.utils.translation import get_language

from .seo_data import (
    DEFAULT_NONPROD_ALLOWLIST,
    SEO_PAGE_CONFIG,
    get_page_key_from_path,
    get_page_key_from_route,
)

CFG_CACHE_KEY = "marketing:global_config"
CFG_CACHE_TTL = 300  # 5 min

CONSENT_TRUE_VALUES = {"1", "true", "yes", "y", "on", "accept"}

def _normalize_consent_value(value: object) -> str:
    if value is None:
        return ""
    try:
        return str(value).strip().lower()
    except Exception:
        return ""

def marketing_consent_cookie_name() -> str:
    return getattr(settings, "CONSENT_COOKIE_NAME", "cookie_consent_marketing")

def is_marketing_consent_enabled(value: object) -> bool:
    return _normalize_consent_value(value) in CONSENT_TRUE_VALUES

def has_marketing_consent(request: HttpRequest | None) -> bool:
    if request is None:
        return False
    try:
        raw_value = request.COOKIES.get(marketing_consent_cookie_name(), "")
    except Exception:
        raw_value = ""
    return is_marketing_consent_enabled(raw_value)

def get_global_defaults() -> dict:
    base = {
        "site_name": getattr(settings, "PROJECT_SITE_NAME", "lumiereacademy"),
        "default_robots": "index,follow",
        "default_locale": getattr(settings, "LANGUAGE_CODE", "fr"),
        "canonical_host": getattr(settings, "SITE_CANONICAL_HOST", ""),
        "meta_defaults": {
            "title": "",
            "description": "",
            "image": "",
            "twitter_site": "",
            "twitter_creator": "",
            "og_app_id": "",
        },
        "gtm_id": "",
        "ga4_id": "",
        "meta_pixel_id": "",
        "tiktok_pixel_id": "",
        "consent_cookie_name": marketing_consent_cookie_name(),
    }
    override = getattr(settings, "MARKETING_DEFAULTS", {})
    if isinstance(override, dict):
        for k, v in override.items():
            if k == "meta_defaults" and isinstance(v, dict):
                base["meta_defaults"].update(v)
            else:
                base[k] = v
    return base

# def _load_db_config() -> dict | None:
#     try:
#         from .models import MarketingConfig
#     except Exception:
#         return None
#     try:
#         obj = MarketingConfig.objects.order_by("-id").first()
#     except Exception:
#         obj = None
#     if not obj:
#         return None
#
#     data = {
#         "site_name": obj.site_name,
#         "default_robots": obj.default_robots,
#         "default_locale": obj.default_locale,
#         "canonical_host": obj.canonical_host,
#         "meta_defaults": {},
#         "gtm_id": getattr(obj, "gtm_id", "") or "",
#         "ga4_id": getattr(obj, "ga4_id", "") or "",
#         "meta_pixel_id": getattr(obj, "meta_pixel_id", "") or "",
#         "tiktok_pixel_id": getattr(obj, "tiktok_pixel_id", "") or "",
#         "consent_cookie_name": getattr(obj, "consent_cookie_name", "") or "",
#     }
#     # Meta defaults (si présents)
#     if getattr(obj, "default_title", None):
#         data["meta_defaults"]["title"] = obj.default_title
#     if getattr(obj, "default_description", None):
#         data["meta_defaults"]["description"] = obj.default_description
#     if getattr(obj, "default_image", None):
#         try:
#             if obj.default_image:
#                 data["meta_defaults"]["image"] = obj.default_image.url
#         except Exception:
#             pass
#     if getattr(obj, "twitter_site", None):
#         data["meta_defaults"]["twitter_site"] = obj.twitter_site
#     if getattr(obj, "twitter_creator", None):
#         data["meta_defaults"]["twitter_creator"] = obj.twitter_creator
#     if getattr(obj, "facebook_app_id", None):
#         data["meta_defaults"]["og_app_id"] = obj.facebook_app_id
#
#     return data

# apps/marketing/helpers.py
def _load_db_config() -> dict | None:
    try:
        # CHANGE: importer MarketingGlobal et pas MarketingConfig
        from apps.marketing.models.models_base import MarketingGlobal
    except Exception:
        return None
    try:
        obj = MarketingGlobal.objects.order_by("-id").first()
    except Exception:
        obj = None
    if not obj:
        return None

    data = {
        "site_name": obj.site_name,
        "default_robots": obj.robots_default,     # CHANGE: champ existant sur MarketingGlobal
        "default_locale": obj.default_locale,
        "canonical_host": obj.base_url,           # si tu stockes l’host canonique là
        "meta_defaults": {},
        "gtm_id": getattr(obj, "gtm_id", "") or "",
        "ga4_id": getattr(obj, "ga4_id", "") or "",
        "meta_pixel_id": getattr(obj, "meta_pixel_id", "") or "",
        "tiktok_pixel_id": getattr(obj, "tiktok_pixel_id", "") or "",
        "consent_cookie_name": getattr(obj, "consent_cookie_name", "") or "",
    }
    # Meta defaults
    if obj.site_name:
        data["meta_defaults"]["title"] = obj.site_name
    if obj.default_image:
        data["meta_defaults"]["image"] = obj.default_image
    # Si tu as des champs "twitter_site", "twitter_creator", "facebook_app_id"
    if obj.twitter_site:
        data["meta_defaults"]["twitter_site"] = obj.twitter_site
    if obj.twitter_creator:
        data["meta_defaults"]["twitter_creator"] = obj.twitter_creator
    if obj.facebook_app_id:
        data["meta_defaults"]["og_app_id"] = obj.facebook_app_id

    return data


def get_global_config() -> dict:
    cached = cache.get(CFG_CACHE_KEY)
    if isinstance(cached, dict):
        return cached

    defaults = get_global_defaults()
    db_cfg = _load_db_config()

    cfg = dict(defaults)
    if db_cfg:
        for k, v in db_cfg.items():
            if k == "meta_defaults":
                cfg["meta_defaults"].update(v or {})
            elif v not in (None, ""):
                cfg[k] = v

    final_override = getattr(settings, "MARKETING_DEFAULTS", {})
    if isinstance(final_override, dict):
        for k, v in final_override.items():
            if k == "meta_defaults" and isinstance(v, dict):
                cfg["meta_defaults"].update(v)
            elif v not in (None, ""):
                cfg[k] = v

    # NEW: alias rétro-compatibles attendus par certains appels existants
    cfg["default_title"] = cfg["meta_defaults"].get("title", "")          # NEW
    cfg["default_description"] = cfg["meta_defaults"].get("description", "")  # NEW
    cfg["default_image"] = cfg["meta_defaults"].get("image", "")          # NEW

    cache.set(CFG_CACHE_KEY, cfg, CFG_CACHE_TTL)
    return cfg

def build_base_url(request) -> str:
    cfg = get_global_config()
    scheme = getattr(request, "scheme", "https") or "https"
    host = cfg.get("canonical_host")

    if not host:
        get_host = getattr(request, "get_host", None)
        if callable(get_host):
            try:
                host = get_host()
            except Exception:
                host = ""
        if not host:
            meta = getattr(request, "META", {}) or {}
            host = meta.get("HTTP_HOST") or meta.get("SERVER_NAME") or "localhost"

    base = f"{scheme}://{host}"
    return base.rstrip("/")

def absolute_url(base: str, path_or_url: str) -> str:
    if not path_or_url:
        return base
    parsed = urlparse(path_or_url)
    if parsed.scheme and parsed.netloc:
        return path_or_url
    if not path_or_url.startswith("/"):
        path_or_url = "/" + path_or_url
    basep = urlparse(base.rstrip("/"))
    return urlunparse((basep.scheme, basep.netloc, path_or_url, "", "", ""))

def clean_canonical(request, allow_params=None) -> str:
    allow_params = allow_params or getattr(settings, "SEO_ALLOWED_QUERY_CANONICAL", [])
    base = build_base_url(request)
    path = getattr(request, "path", "/")
    try:
        qs_items = {k: request.GET.get(k) for k in allow_params if k in request.GET}
        query = urlencode(qs_items) if qs_items else ""
    except Exception:
        query = ""
    return urlunparse((urlparse(base).scheme, urlparse(base).netloc, path, "", query, ""))

def _infer_page_key(request, explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    route_name = getattr(getattr(request, "resolver_match", None), "view_name", None)
    page_from_route = get_page_key_from_route(route_name)
    if page_from_route:
        return page_from_route
    path = getattr(request, "path", None)
    return get_page_key_from_path(path)


def robots_directive(
    request,
    *,
    page_key: str | None = None,
    override: dict | None = None,
    default_public: bool = True,
    force_noindex: bool = False,
    preview: bool = False,
) -> str:
    """Resolve the <meta name="robots"> directive for a request."""

    override = override or {}
    explicit = override.get("robots") if isinstance(override, dict) else None
    if explicit:
        return str(explicit)

    if force_noindex:
        return "noindex,nofollow"
    if preview:
        return "noindex,nofollow"

    resolved_page = _infer_page_key(request, explicit=page_key)

    env = getattr(settings, "SEO_ENV", "dev") or "dev"
    nonprod = env != "prod"
    if nonprod and getattr(settings, "SEO_FORCE_NOINDEX_NONPROD", True):
        raw_allow = getattr(settings, "SEO_NONPROD_INDEX_ALLOWLIST", None)
        if raw_allow:
            allowlist = {str(item) for item in raw_allow}
        else:
            allowlist = set(DEFAULT_NONPROD_ALLOWLIST)
        if resolved_page not in allowlist:
            return "noindex,nofollow"

    if resolved_page and resolved_page in SEO_PAGE_CONFIG:
        return SEO_PAGE_CONFIG[resolved_page].robots

    cfg = get_global_config()
    default_value = cfg.get("default_robots", "index,follow")
    return default_value if default_public else "noindex,nofollow"

def lang_hreflangs(request):
    lang = get_language() or (getattr(settings, "LANGUAGE_CODE", "fr") or "fr")
    return [(lang, clean_canonical(request))]

def pagination_links(request, page_obj):
    prev_url = next_url = None
    if not page_obj:
        return prev_url, next_url
    base_with_page = clean_canonical(request, allow_params=["page"])
    parsed = urlparse(base_with_page)
    if page_obj.has_previous():
        prev_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", urlencode({"page": page_obj.previous_page_number()}), ""))
    if page_obj.has_next():
        next_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", urlencode({"page": page_obj.next_page_number()}), ""))
    return prev_url, next_url
