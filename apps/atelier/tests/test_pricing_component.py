from __future__ import annotations

from types import SimpleNamespace

from django.test import RequestFactory, TestCase

from apps.pages.views import PacksView


class PricingComponentRenderTests(TestCase):
    factory = RequestFactory()

    def _request(self):
        request = self.factory.get("/packs")
        request.site_version = "core"
        request._segments = SimpleNamespace(lang="fr", device="desktop", consent="N", source="", campaign="", qa=False)
        request.GET = {}
        request.COOKIES = {}
        request.META = {
            "HTTP_USER_AGENT": "pytest",
            "SERVER_NAME": "testserver",
            "SERVER_PORT": "80",
            "wsgi.url_scheme": "http",
        }
        request.headers = {"Accept-Language": "fr"}
        request.user = SimpleNamespace(is_authenticated=False)
        return request

    def test_packs_page_renders_pricing_heading(self) -> None:
        request = self._request()
        response = PacksView.as_view()(request)
        response.render()

        self.assertEqual(response.status_code, 200)
        self.assertIn("<h2 class=\"pricing-title text-center\">Et tout ça pour seulement…</h2>", response.rendered_content)

    def test_http_endpoints_return_200(self) -> None:
        resp_home = self.client.get("/")
        self.assertEqual(resp_home.status_code, 200)

        resp_packs = self.client.get("/packs")
        self.assertEqual(resp_packs.status_code, 200)
