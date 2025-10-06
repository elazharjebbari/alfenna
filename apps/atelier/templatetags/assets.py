from __future__ import annotations

from django import template

register = template.Library()

_VENDOR_PATTERNS = (
    "/vendors/",
    "/vendor/",
    "cdn.jsdelivr.net",
    "cdnjs.cloudflare.com",
    "/cookies/tarteaucitron.js-",
    "/static/js/vendor/",
    "/static/js/plugins.js",
    "/static/js/bootstrap.bundle.min.js",
    "/static/js/main.js",
    "/static/site/core.js",
    "/static/css/plugins/",
    "/static/site/core.css",
    "/static/css/style.css",
)


@register.filter(name="exclude_known_vendors")
def exclude_known_vendors(urls):
    if not urls:
        return []
    cleaned = []
    for url in urls:
        value = str(url or "")
        if not any(pattern in value for pattern in _VENDOR_PATTERNS):
            cleaned.append(value)
    return cleaned
