from __future__ import annotations
import unittest

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings

from apps.marketing.models.models_pricing import PricePlan

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover - optional dependency
    sync_playwright = None


@override_settings(ENABLE_PLAYWRIGHT_TESTS=True)
class ProductPageFRE2E(StaticLiveServerTestCase):
    fixtures = ["alfenna/fixtures/product_pack_cosmetique_naturel.json"]
    @classmethod
    def setUpClass(cls):
        if sync_playwright is None:
            raise unittest.SkipTest("Playwright absent (pip install playwright && playwright install)")
        try:
            super().setUpClass()
        except PermissionError as exc:
            raise unittest.SkipTest(f"LiveServer indisponible ({exc})") from exc

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "server_thread", None):
            super().tearDownClass()

    @classmethod
    def setUpTestData(cls):
        plan, _ = PricePlan.objects.get_or_create(
            slug="createur",
            defaults=dict(
                title="Createur",
                currency="MAD",
                currency_symbol="MAD",
                price_cents=32900,
                is_active=True,
            ),
        )
        plan.title = "TITRE_DB_SENTINEL"
        plan.features = ["FEATURE_DB_SENTINEL"]
        plan.save()

    def test_product_page_fr_renders_db_values(self):
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(ignore_https_errors=True)
            context.add_cookies(
                [
                    {
                        "name": getattr(settings, "CONSENT_COOKIE_NAME", "cookie_consent_marketing"),
                        "value": "yes",
                        "url": self.live_server_url,
                    }
                ]
            )
            page = context.new_page()

            candidates = (
                "/produits/pack-cosmetique-naturel/",
                "/maroc/produits/pack-cosmetique-naturel/",
                "/maroc/fr/produits/pack-cosmetique-naturel/",
            )
            ok_url = None
            for candidate in candidates:
                try:
                    response = page.goto(self.live_server_url + candidate, wait_until="networkidle")
                except Exception:
                    continue
                if response and response.status == 200:
                    ok_url = candidate
                    break
            self.assertIsNotNone(ok_url, f"Aucune URL candidate n'a rendu 200: {candidates}")

            page.wait_for_selector(
                '[data-ll-slot-id="sticky_buybar"], [data-ll-slot-id="sticky_buybar_v2"], .vs-sticky',
                timeout=10000,
            )

            html = page.content()
            misses = [needle for needle in ("TITRE_DB_SENTINEL", "FEATURE_DB_SENTINEL") if needle not in html]
            if misses:
                page.screenshot(path="product_fr_e2e_debug.png", full_page=True)
                self.fail(f"Absence sentinelles DB: {misses} sur {ok_url}")

            context.close()
            browser.close()
