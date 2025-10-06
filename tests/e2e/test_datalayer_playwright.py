from __future__ import annotations

import unittest

from django.conf import settings
from django.contrib.staticfiles import storage as staticfiles_storage_module
from django.contrib.staticfiles.storage import StaticFilesStorage
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings

from playwright.sync_api import sync_playwright


@override_settings(STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage")
@unittest.skipIf(not getattr(settings, "ENABLE_PLAYWRIGHT_TESTS", False), "Playwright analytics suite disabled")
class DataLayerE2ETests(StaticLiveServerTestCase):
    def setUp(self):
        super().setUp()
        self._original_staticfiles_storage = staticfiles_storage_module.staticfiles_storage
        staticfiles_storage_module.staticfiles_storage = StaticFilesStorage()

    def tearDown(self):
        staticfiles_storage_module.staticfiles_storage = self._original_staticfiles_storage
        super().tearDown()

    def test_consent_yes_initializes_data_layer(self):
        consent_cookie = getattr(settings, "CONSENT_COOKIE_NAME", "cookie_consent_marketing")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context()
            context.add_cookies([
                {"name": consent_cookie, "value": "yes", "url": self.live_server_url},
            ])
            page = context.new_page()
            try:
                page.goto(f"{self.live_server_url}/", wait_until="networkidle")
                page.wait_for_function("() => window.dataLayer && window.dataLayer.__llWrapped === true", timeout=20000)
                page.evaluate("window.dataLayer.push({ event_type: 'scroll', payload: { depth: 50 } })")
                page.wait_for_function("() => window.dataLayer.length > 0", timeout=3000)
                event = page.evaluate("window.dataLayer[window.dataLayer.length - 1]")
                self.assertEqual(event.get("event_type"), "scroll")
                self.assertIn("event_uuid", event)
                self.assertIn("ts", event)
            finally:
                context.close()
                browser.close()

    def test_consent_no_leaves_wrapper_disabled(self):
        consent_cookie = getattr(settings, "CONSENT_COOKIE_NAME", "cookie_consent_marketing")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context()
            context.add_cookies([
                {"name": consent_cookie, "value": "n", "url": self.live_server_url},
            ])
            page = context.new_page()
            try:
                page.goto(f"{self.live_server_url}/", wait_until="networkidle")
                wrapped = page.evaluate("Boolean(window.dataLayer && window.dataLayer.__llWrapped)")
                script_present = page.query_selector("script[src$='site/analytics.js']")
                self.assertFalse(wrapped)
                self.assertIsNone(script_present)
            finally:
                context.close()
                browser.close()
