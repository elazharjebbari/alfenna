from __future__ import annotations

from django.conf import settings
from django.test import Client, TestCase, override_settings


_TEST_STORAGES = {
    **dict(settings.STORAGES),
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=_TEST_STORAGES)
class PagesVersionsIntegrationTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()

    @staticmethod
    def _context(response):
        ctx = getattr(response, "context", None)
        if ctx is None:
            return {}
        if isinstance(ctx, list):
            return ctx[0] if ctx else {}
        return ctx

    def test_home_core_ok(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        response.render()
        ctx = self._context(response)
        meta = ctx.get("meta")
        self.assertTrue(getattr(meta, "title", ""))

    def test_home_ma_ok(self) -> None:
        response = self.client.get("/maroc/")
        self.assertEqual(response.status_code, 200)
        response.render()
        ctx = self._context(response)
        meta = ctx.get("meta")
        self.assertTrue(getattr(meta, "title", ""))
        self.assertContains(response, "Version Maroc")

    def test_home_fr_ok(self) -> None:
        response = self.client.get("/france/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "+33 1 23 45 67 89")

    def test_single_title_tag_rendered_once_per_namespace(self) -> None:
        for path in ["/", "/maroc/"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            html = response.content.decode("utf-8")
            self.assertEqual(html.count("<title"), 1, path)
            self.assertEqual(html.count("</title>"), 1, path)

    def test_gtm_injected_at_most_once_with_consent(self) -> None:
        consent_cookie = getattr(settings, "CONSENT_COOKIE_NAME", "cookie_consent_marketing")
        self.client.cookies[consent_cookie] = "yes"

        for path in ["/", "/maroc/"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            response.render()
            ctx = self._context(response)
            cfg = ctx.get("marketing_config", {})
            gtm_id = cfg.get("gtm_id")
            html = response.content.decode("utf-8")
            head_count = html.count("https://www.googletagmanager.com/gtm.js")
            body_count = html.count("https://www.googletagmanager.com/ns.html")
            expected = 1 if gtm_id else 0
            self.assertEqual(head_count, expected, path)
            self.assertEqual(body_count, expected, path)

    def test_all_pages_exist_both_versions(self) -> None:
        routes = ["", "contact", "courses", "test"]
        for route in routes:
            core_path = f"/{route}" if route else "/"
            ma_path = f"/maroc/{route}" if route else "/maroc/"
            resp_core = self.client.get(core_path)
            resp_ma = self.client.get(ma_path)
            self.assertEqual(resp_core.status_code, 200, core_path)
            self.assertEqual(resp_ma.status_code, 200, ma_path)

    def test_cache_isolation(self) -> None:
        core_response = self.client.get("/")
        ma_response = self.client.get("/maroc/")

        core_response.render()
        ma_response.render()

        core_meta = core_response.context_data["page_meta"]["title"]
        ma_meta = ma_response.context_data["page_meta"]["title"]
        self.assertNotEqual(core_meta, ma_meta)

    def test_namespace_page_renders_override(self) -> None:
        response = self.client.get("/maroc/")
        self.assertContains(response, "Version Maroc")

    def test_namespace_isolation(self) -> None:
        core_response = self.client.get("/")
        self.assertNotContains(core_response, "Version Maroc")
