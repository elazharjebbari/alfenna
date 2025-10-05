from __future__ import annotations

from django.test import Client, TestCase, override_settings


@override_settings(
    COMPRESS_ENABLED=True,
    COMPRESS_OFFLINE=False,
    ATELIER_DISABLE_REGISTERED_ASSETS=True,
)
class ConsentBundlesE2ETest(TestCase):
    def test_e2e_consent_and_bundles(self) -> None:
        response = Client().get("/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn("tarteaucitron", html)
        self.assertIn("ll_consent_update", html)
        self.assertTrue(
            "/static/js/main.js" in html or "/static/CACHE/js/" in html
        )
        self.assertNotIn("/static/js/vendor/modernizr-3.11.2.min.js", html)
