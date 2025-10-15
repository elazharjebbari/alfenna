from __future__ import annotations

from types import SimpleNamespace

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from apps.atelier.middleware.vary import VaryHeadersMiddleware


class VaryHeadersMiddlewareTests(SimpleTestCase):
    factory = RequestFactory()

    def test_vary_header_includes_site_version_and_lang(self) -> None:
        request = self.factory.get("/")
        request.site_version = "ma"
        request._segments = SimpleNamespace(
            lang="ar",
            device="d",
            consent="N",
            source="",
            campaign="",
            qa=False,
        )

        def _get_response(_request):
            response = HttpResponse()
            response["Vary"] = "Accept-Language"
            return response

        middleware = VaryHeadersMiddleware(_get_response)
        response = middleware(request)

        vary_values = {entry.strip() for entry in response["Vary"].split(",")}
        self.assertIn("lang", vary_values)
        self.assertIn("site_version", vary_values)
