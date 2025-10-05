# apps/marketing/schema.py
from __future__ import annotations

from django.templatetags.static import static

from .helpers import get_global_config, build_base_url, absolute_url


def website_schema(request=None) -> dict:
    """
    WebSite minimal, safe par défaut.
    """
    cfg = get_global_config()
    base = ""
    if request:
        base = build_base_url(request)
    data = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": cfg.get("site_name", "Site"),
    }
    if request:
        data["url"] = base
    return data


def org_schema(request=None) -> dict:
    """
    Organization avec logo par défaut si dispo.
    """
    cfg = get_global_config()
    base = build_base_url(request) if request else ""
    logo = (
        cfg.get("default_image")
        or cfg.get("meta_defaults", {}).get("image")
        or static("img/logo.png")
    )
    if base:
        logo = absolute_url(base, logo)
    return {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": cfg.get("site_name", "Site"),
        "logo": logo,
        # Optionnel: "url": base,
    }


def course_schema(course, request) -> dict:
    """
    Course JSON-LD robuste (image/price facultatifs).
    """
    cfg = get_global_config()
    base = build_base_url(request)

    # Image : cours > config > placeholder statique
    img = getattr(course, "image", None)
    img_url = None
    try:
        if img:
            img_url = img.url
    except Exception:
        img_url = None
    if not img_url:
        img_url = cfg.get("default_image") or cfg.get("meta_defaults", {}).get("image") or static("img/placeholder.png")
    img_url = absolute_url(base, img_url)

    data = {
        "@context": "https://schema.org",
        "@type": "Course",
        "name": (getattr(course, "seo_title", None) or getattr(course, "title", ""))[:200],
        "description": (getattr(course, "seo_description", None) or getattr(course, "description", "") or "")[:1000],
        "url": absolute_url(base, course.get_absolute_url()),
        "image": img_url,
        "provider": {
            "@type": "Organization",
            "name": cfg.get("site_name", "Site"),
        },
    }

    # Option: Offer si tu as un prix accessible facilement
    try:
        # Adapte cette logique à ton modèle/pricing (ex: course.prices.first() ...)
        if hasattr(course, "get_public_price"):
            price_obj = course.get_public_price()
            if price_obj and getattr(price_obj, "amount", None):
                currency = getattr(price_obj, "currency", "EUR")
                amount = getattr(price_obj, "amount")  # supposé en unités (ex: 99.00)
                data["offers"] = {
                    "@type": "Offer",
                    "priceCurrency": currency,
                    "price": str(amount),
                    "availability": "https://schema.org/InStock",
                    "url": data["url"],
                }
    except Exception:
        # Silent: on n'empêche jamais le rendu du JSON-LD
        pass

    return data


def article_schema(lecture, request) -> dict:
    """JSON-LD minimal pour une leçon publiée."""
    course = getattr(lecture, "course", None)
    base = build_base_url(request)
    cfg = get_global_config()

    url = absolute_url(base, lecture.get_absolute_url())
    course_url = absolute_url(base, course.get_absolute_url()) if course else base

    data = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": getattr(lecture, "title", ""),
        "url": url,
        "isAccessibleForFree": bool(getattr(lecture, "is_free", False)),
        "inLanguage": cfg.get("default_locale", "fr"),
        "publisher": {
            "@type": "Organization",
            "name": cfg.get("site_name", "Site"),
        },
    }

    if course:
        data["partOfSeries"] = {
            "@type": "Course",
            "name": getattr(course, "title", ""),
            "url": course_url,
        }

    # Dates ISO si dispo
    created = getattr(lecture, "created_at", None)
    if created:
        try:
            data["datePublished"] = created.isoformat()
        except Exception:
            pass
    updated = getattr(lecture, "updated_at", None)
    if updated:
        try:
            data["dateModified"] = updated.isoformat()
        except Exception:
            pass

    return data
