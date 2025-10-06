# apps/marketing/context_processors.py
from __future__ import annotations

import logging

from django.conf import settings
from django.urls import resolve
from meta.views import Meta

from .helpers import (
    get_global_config,
    clean_canonical,
    build_base_url,
    absolute_url,
    robots_directive,
    lang_hreflangs,
    pagination_links,
)
from .seo_data import (
    SEO_PAGE_CONFIG,
    get_page_key_from_path,
    get_page_key_from_route,
)


log = logging.getLogger("marketing.seo")


def _format_value(template, context):
    if not template:
        return ""
    if "{" in template:
        try:
            return template.format(**context)
        except Exception:
            return template
    return template


def _normalize_override(raw):
    if not isinstance(raw, dict):
        return {}
    normalized = {}
    mapping = {
        "title": "title",
        "meta_title": "title",
        "description": "description",
        "meta_description": "description",
        "image": "image",
        "meta_image": "image",
        "object_type": "og_type",
        "meta_type": "og_type",
        "url": "url",
        "meta_url": "url",
        "robots": "robots",
        "twitter_card": "twitter_card",
        "twitter_site": "twitter_site",
        "twitter_creator": "twitter_creator",
    }
    for key, value in raw.items():
        target = mapping.get(key)
        if target and value:
            normalized[target] = value
    return normalized


def seo(request):
    """
    Orchestrateur global :
    - expose config, canonical absolu, robots final, hreflang, prev/next
    - tracking + consent (placeholders) ; l’injection des tags est gérée par tes partials
    - 'meta' (django-meta) est exposé par 'meta.context_processors.meta' si installé
    """
    cfg = get_global_config()
    site_name = cfg.get("site_name", "Site")
    context_vars = {"site_name": site_name}

    # Sécurité : route (peut échouer pour certaines URLs spéciales)
    try:
        route_name = resolve(request.path_info).view_name
    except Exception:
        route_name = ""

    page_key = get_page_key_from_route(route_name) or get_page_key_from_path(getattr(request, "path", ""))
    if page_key:
        request._seo_page_key = page_key  # debug helper
    placeholder = SEO_PAGE_CONFIG.get(page_key)

    # Prévisualisation & overrides (possibles via middleware/vue)
    preview = bool(request.GET.get("preview"))
    override = getattr(request, "_meta_override", {}) or {}
    force_noindex = bool(override.get("noindex"))
    view_override = _normalize_override(getattr(request, "_seo_override", {}))

    # Canonical & robots
    try:
        canonical = clean_canonical(request)
    except Exception:
        canonical = ""  # fallback ultra défensif
    if view_override.get("url"):
        canonical = absolute_url(build_base_url(request), view_override["url"])
    robots = robots_directive(
        request,
        page_key=page_key,
        override=view_override,
        preview=preview,
        force_noindex=force_noindex,
    )

    # Hreflang
    alternates = []
    if getattr(settings, "MARKETING_ENABLE_HREFLANGS", True):
        try:
            alternates = lang_hreflangs(request)
        except Exception:
            alternates = []

    # Pagination (si la vue a accroché page_obj au request)
    page_obj = getattr(request, "page_obj", None)
    prev_link, next_link = pagination_links(request, page_obj)

    title_source = "global"
    title_value = view_override.get("title")
    if title_value:
        title_source = "view"
    elif placeholder and placeholder.title:
        title_value = _format_value(placeholder.title, context_vars)
        title_source = "placeholder"
    else:
        title_value = cfg.get("meta_defaults", {}).get("title") or site_name

    description_value = view_override.get("description")
    if not description_value and placeholder and placeholder.description:
        description_value = _format_value(placeholder.description, context_vars)
    if not description_value:
        description_value = cfg.get("meta_defaults", {}).get("description", "")

    og_type = view_override.get("og_type") or (placeholder.og_type if placeholder else "website") or "website"
    twitter_card = view_override.get("twitter_card") or (placeholder.twitter_card if placeholder else "summary_large_image")
    twitter_site = view_override.get("twitter_site") or cfg.get("meta_defaults", {}).get("twitter_site") or ""
    twitter_creator = view_override.get("twitter_creator") or cfg.get("meta_defaults", {}).get("twitter_creator") or ""

    base_url = build_base_url(request)
    image_value = view_override.get("image") or (placeholder.image if placeholder else cfg.get("meta_defaults", {}).get("image"))
    if not image_value:
        image_value = cfg.get("default_image")
    image_absolute = absolute_url(base_url, image_value) if image_value else ""

    meta_obj = Meta(
        title=title_value or None,
        description=description_value or None,
        image=image_absolute or None,
        url=canonical or None,
        object_type=og_type,
        site_name=site_name,
        twitter_site=twitter_site or None,
        twitter_creator=twitter_creator or None,
        twitter_card=twitter_card or "summary_large_image",
        og_app_id=cfg.get("meta_defaults", {}).get("og_app_id") or None,
        use_title_tag=True,
    )

    # Tracking + consent
    consent_cookie = cfg.get("consent_cookie_name", "cookie_consent_marketing")
    consent_value = (request.COOKIES.get(consent_cookie) or "").lower() in ("1", "true", "yes", "accept")
    tracking = {
        "consent": consent_value,
        "GTM_ID": cfg.get("gtm_id", ""),
        "GA4_ID": cfg.get("ga4_id", ""),
        "META_PIXEL_ID": cfg.get("meta_pixel_id", ""),
        "TIKTOK_PIXEL_ID": cfg.get("tiktok_pixel_id", ""),
        "datalayer": {
            "page_type": route_name or "",
            "path": getattr(request, "path", "") or "",
            "lang": getattr(request, "LANGUAGE_CODE", None) or "",  # django-meta fournit déjà lang côté <meta> si besoin
        },
        "analytics_enabled": getattr(settings, "ANALYTICS_ENABLED", True),
    }

    seo_meta = {
        "canonical": canonical,
        "robots": robots,
        "alternates": alternates,
        "prev_link": prev_link,
        "next_link": next_link,
        "site_name": site_name,
        "page_key": page_key,
        "title": title_value,
        "description": description_value,
        "image": image_absolute,
        "og_type": og_type,
        "twitter_card": twitter_card,
    }

    log.info(
        "seo.resolved path=%s route=%s page=%s robots=%s canonical=%s title_source=%s",
        getattr(request, "path", ""),
        route_name or "-",
        page_key or "-",
        robots or "-",
        canonical or "-",
        title_source,
    )

    return {
        "seo_meta": seo_meta,
        "meta": meta_obj,
        "tracking": tracking,
        "marketing_config": cfg,
    }
