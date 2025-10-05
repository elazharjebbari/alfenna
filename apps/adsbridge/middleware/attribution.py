from __future__ import annotations

import json
import logging
from typing import Any, Callable

from django.conf import settings
from django.core import signing
from django.http import HttpRequest, HttpResponse

from apps.marketing.helpers import has_marketing_consent, marketing_consent_cookie_name

logger = logging.getLogger("adsbridge")

ATTR_COOKIE_NAME = getattr(settings, "ADSBRIDGE_ATTRIBUTION_COOKIE", "ll_ads_attr")
CONSENT_COOKIE_NAME = marketing_consent_cookie_name()
MAX_AGE_SECONDS = 90 * 24 * 3600
_TRACKED_KEYS = ("gclid", "gbraid", "wbraid", "gclsrc")
_SALT = "adsbridge.attribution"


class AttributionMiddleware:
    """Persist Google Ads attribution identifiers when marketing consent is granted."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        consent_granted = self._has_marketing_consent(request)
        attribution = self._load_cookie(request) if consent_granted else {}

        query_updates = self._extract_query_ids(request)
        should_persist = False

        if query_updates and consent_granted:
            attribution.update(query_updates)
            should_persist = True

        request._attribution = attribution

        response = self.get_response(request)

        if not consent_granted:
            if ATTR_COOKIE_NAME in request.COOKIES:
                logger.debug("ads_attr_remove_cookie consent=N")
                response.delete_cookie(ATTR_COOKIE_NAME, path="/")
            return response

        if should_persist:
            payload = json.dumps(attribution, separators=(",", ":"))
            response.set_signed_cookie(
                key=ATTR_COOKIE_NAME,
                value=payload,
                salt=_SALT,
                max_age=MAX_AGE_SECONDS,
                path="/",
                secure=getattr(settings, "SESSION_COOKIE_SECURE", False),
                httponly=False,
                samesite=getattr(settings, "SESSION_COOKIE_SAMESITE", "Lax"),
            )
            logger.debug("ads_attr_set_cookie keys=%s", list(query_updates))

        return response

    @staticmethod
    def _has_marketing_consent(request: HttpRequest) -> bool:
        return has_marketing_consent(request)

    @staticmethod
    def _extract_query_ids(request: HttpRequest) -> dict[str, str]:
        updates: dict[str, str] = {}
        for key in _TRACKED_KEYS:
            value = request.GET.get(key)
            if value:
                clean_value = value.strip()[:255]
                if clean_value:
                    updates[key] = clean_value
        return updates

    @staticmethod
    def _load_cookie(request: HttpRequest) -> dict[str, Any]:
        try:
            raw_cookie = request.get_signed_cookie(ATTR_COOKIE_NAME, default=None, salt=_SALT)
        except signing.BadSignature:
            logger.warning("ads_attr_bad_signature cookie invalid")
            return {}
        if not raw_cookie:
            return {}
        try:
            data = json.loads(raw_cookie)
        except json.JSONDecodeError:
            return {}
        if not isinstance(data, dict):
            return {}
        return {k: str(v) for k, v in data.items() if k in _TRACKED_KEYS}
