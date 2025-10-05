"""Robots header middleware ensuring public pages stay indexable."""

from __future__ import annotations

from typing import Iterable, Tuple

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

try:
    from apps.marketing.middleware import SeoGuardMiddleware
except ImportError:  # pragma: no cover - defensive guard for missing app
    SeoGuardMiddleware = None  # type: ignore[assignment]


class RobotsTagMiddleware(MiddlewareMixin):
    """Guarantee consistent ``X-Robots-Tag`` headers for public and private routes."""

    _seo_guard_prefixes: Tuple[str, ...] = ()
    if SeoGuardMiddleware is not None:
        _seo_guard_prefixes = getattr(SeoGuardMiddleware, "BLOCK_PATH_PREFIXES", ())

    _extra_private: Iterable[str] = getattr(
        settings,
        "SEO_EXTRA_PRIVATE_PATH_PREFIXES",
        ("/admin/", "/staging/"),
    )

    # Preserve declaration order while removing duplicates
    PRIVATE_PATH_PREFIXES: Tuple[str, ...] = tuple(
        dict.fromkeys(tuple(_seo_guard_prefixes) + tuple(_extra_private))
    )

    def process_response(self, request, response):  # type: ignore[override]
        path = request.path or ""

        if any(path.startswith(prefix) for prefix in self.PRIVATE_PATH_PREFIXES):
            response["X-Robots-Tag"] = "noindex, nofollow"
            return response

        if "X-Robots-Tag" not in response:
            response["X-Robots-Tag"] = "index, follow"

        return response
