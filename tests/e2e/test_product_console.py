from __future__ import annotations

import unittest

from django.conf import settings
from django.contrib.staticfiles import storage as staticfiles_storage_module
from django.contrib.staticfiles.storage import StaticFilesStorage
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from playwright.sync_api import sync_playwright


@override_settings(
    STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage",
    ENABLE_PLAYWRIGHT_TESTS=True,
)
class ProductConsoleE2ETests(StaticLiveServerTestCase):
    def setUp(self):
        super().setUp()
        self._original_staticfiles_storage = staticfiles_storage_module.staticfiles_storage
        staticfiles_storage_module.staticfiles_storage = StaticFilesStorage()

    def tearDown(self):
        staticfiles_storage_module.staticfiles_storage = self._original_staticfiles_storage
        super().tearDown()

    def test_product_page_has_no_console_errors(self):
        errors: list[str] = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.on("console", lambda msg: errors.append(msg.text()) if msg.type() == "error" else None)
            try:
                page.goto(f"{self.live_server_url}/produits/", wait_until="networkidle")
                page.wait_for_selector('[data-cmp="product"]', timeout=10000)
                if page.locator('#tarteaucitronRoot').count():
                    page.locator('#tarteaucitronRoot').evaluate("node => node.style.display = 'none'")
                nav = page.locator('[data-product-nav="next"]').first
                if nav.count():
                    nav.scroll_into_view_if_needed()
                step_button = page.locator('[data-form-stepper] [data-next]').first
                if step_button.count():
                    step_button.scroll_into_view_if_needed()
                self.assertEqual(errors, [], f"Console errors detected: {errors}")
            finally:
                context.close()
                browser.close()
