from __future__ import annotations

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from apps.adsbridge.middleware.attribution import (
    ATTR_COOKIE_NAME,
    CONSENT_COOKIE_NAME,
    AttributionMiddleware,
)


class AttributionMiddlewareTests(SimpleTestCase):
    factory = RequestFactory()

    def get_response(self, request):
        return HttpResponse("ok")

    def test_sets_cookie_when_consent_and_gclid(self) -> None:
        middleware = AttributionMiddleware(self.get_response)
        request = self.factory.get("/", {"gclid": "G1"})
        request.COOKIES[CONSENT_COOKIE_NAME] = "true"

        response = middleware(request)

        self.assertEqual(request._attribution.get("gclid"), "G1")
        self.assertIn(ATTR_COOKIE_NAME, response.cookies)

    def test_loads_existing_cookie(self) -> None:
        middleware = AttributionMiddleware(self.get_response)

        first_request = self.factory.get("/", {"gclid": "OLD"})
        first_request.COOKIES[CONSENT_COOKIE_NAME] = "true"
        first_response = middleware(first_request)
        signed_value = first_response.cookies[ATTR_COOKIE_NAME].value

        second_request = self.factory.get("/")
        second_request.COOKIES[CONSENT_COOKIE_NAME] = "true"
        second_request.COOKIES[ATTR_COOKIE_NAME] = signed_value

        second_response = middleware(second_request)

        self.assertEqual(second_request._attribution.get("gclid"), "OLD")
        self.assertNotIn(ATTR_COOKIE_NAME, second_response.cookies)

    def test_no_cookie_when_no_consent(self) -> None:
        middleware = AttributionMiddleware(self.get_response)
        request = self.factory.get("/", {"gclid": "NOPE"})
        response = middleware(request)

        self.assertFalse(response.cookies)
        self.assertEqual(getattr(request, "_attribution", {}), {})
