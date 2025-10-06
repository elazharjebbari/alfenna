from __future__ import annotations

import re

import unittest

from django.conf import settings
from django.contrib.staticfiles import storage as staticfiles_storage_module
from django.contrib.staticfiles.storage import StaticFilesStorage
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright


@override_settings(STATICFILES_STORAGE="django.contrib.staticfiles.storage.StaticFilesStorage")
@unittest.skipIf(not getattr(settings, "ENABLE_PLAYWRIGHT_TESTS", False), "Playwright analytics suite disabled for CLI tests")
class AnalyticsDataLayerIntegrationTests(StaticLiveServerTestCase):
    def setUp(self):
        super().setUp()
        self._original_staticfiles_storage = staticfiles_storage_module.staticfiles_storage
        staticfiles_storage_module.staticfiles_storage = StaticFilesStorage()

    def tearDown(self):
        staticfiles_storage_module.staticfiles_storage = self._original_staticfiles_storage
        super().tearDown()

    def test_datalayer_push_dispatches_custom_event_with_consent(self):
        consent_cookie = getattr(settings, "CONSENT_COOKIE_NAME", "cookie_consent_marketing")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context()
            context.add_cookies([
                {"name": consent_cookie, "value": "yes", "url": self.live_server_url},
            ])
            page = context.new_page()
            try:
                response = page.goto(f"{self.live_server_url}/", wait_until="networkidle")
                self.assertIsNotNone(response, "No response from live server")
                self.assertEqual(response.status, 200, f"Unexpected status {response.status} {response.status_text}")
                page.wait_for_timeout(500)
                try:
                    page.wait_for_function(
                        "() => window.dataLayer && window.dataLayer.__llWrapped === true",
                        timeout=20000,
                    )
                except PlaywrightTimeoutError:
                    snapshot = page.evaluate(
                        """
                        () => ({
                            cookies: document.cookie,
                            hasDL: !!window.dataLayer,
                            wrapped: window.dataLayer && window.dataLayer.__llWrapped,
                            htmlHasScript: !!document.querySelector('script[src*="site/analytics.js"]'),
                            analyticsEnabled: document.body ? document.body.getAttribute('data-ll-analytics-enabled') : null,
                            consentAttr: document.body ? document.body.getAttribute('data-ll-consent-cookie') : null,
                            url: window.location.href
                        })
                        """
                    )
                    markup_preview = page.content()[:2000]
                    self.fail(f"DataLayer not initialised: {snapshot} markup={markup_preview}")
                page.evaluate(
                    """
                    () => {
                        window.__dlCaptured = [];
                        window.addEventListener('datalayer:push', (ev) => {
                            window.__dlCaptured.push(ev.detail);
                        });
                    }
                    """
                )
                page.evaluate("window.dataLayer.push({ event_type: 'view', page_id: 'home' })")
                page.wait_for_function("() => window.__dlCaptured.length === 1", timeout=5000)
                event = page.evaluate("window.__dlCaptured[0]")
                self.assertEqual(event.get("page_id"), "home")
                self.assertTrue(event.get("event_uuid"))
                self.assertRegex(event.get("ts") or "", r"^\d{4}-\d{2}-\d{2}T")
                dl_length = page.evaluate("window.dataLayer.length")
                self.assertGreaterEqual(dl_length, 1)
            finally:
                context.close()
                browser.close()

    def test_datalayer_absent_without_consent(self):
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
                script_present = page.query_selector("script[src$='site/analytics.js']")
                wrapped = page.evaluate("Boolean(window.dataLayer && window.dataLayer.__llWrapped)")
                self.assertIsNone(script_present)
                self.assertFalse(wrapped)
            finally:
                context.close()
                browser.close()
