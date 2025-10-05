"""AB bucketing middleware for deterministic cookie assignment."""

from __future__ import annotations

import secrets

from django.conf import settings


class ABBucketingCookieMiddleware:
    """Ensure every request carries the ll_ab cookie for bucketing."""

    COOKIE_NAME = "ll_ab"
    MAX_AGE = 180 * 24 * 3600  # 6 months

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        new_cookie_value: str | None = None
        if self.COOKIE_NAME not in request.COOKIES:
            new_cookie_value = secrets.token_hex(16)
            request.COOKIES[self.COOKIE_NAME] = new_cookie_value

        response = self.get_response(request)

        if new_cookie_value:
            response.set_cookie(
                self.COOKIE_NAME,
                new_cookie_value,
                max_age=self.MAX_AGE,
                httponly=False,
                samesite="Lax",
                secure=not settings.DEBUG,
                path="/",
            )

        return response
