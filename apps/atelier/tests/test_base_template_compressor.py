from __future__ import annotations

from django.test import Client, TestCase, override_settings


@override_settings(
    COMPRESS_ENABLED=True,
    COMPRESS_OFFLINE=False,
    ATELIER_DISABLE_REGISTERED_ASSETS=True,
)
class BaseTemplateCompressorTest(TestCase):
    def test_homepage_renders_without_registry_assets_and_with_compress_blocks(self) -> None:
        response = Client().get("/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn("tarteaucitron", html)
        self.assertTrue(
            "/static/css/plugins/icofont.min.css" in html
            or "/static/CACHE/css/" in html
        )
        self.assertNotIn("/static/js/vendor/modernizr-3.11.2.min.js", html)
