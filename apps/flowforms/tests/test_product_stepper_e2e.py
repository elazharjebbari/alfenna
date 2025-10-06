from __future__ import annotations

import json
import re
from typing import Any, Dict

from django.conf import settings
from django.test import StaticLiveServerTestCase, override_settings

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover - playwright absent
    sync_playwright = None  # type: ignore


def _canonical(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except Exception:
            return {}
    if not isinstance(obj, dict):
        return {}
    drop = {"signed_token", "csrfmiddlewaretoken"}
    filtered = {k: v for k, v in obj.items() if k not in drop}
    return json.loads(json.dumps(filtered, sort_keys=True, separators=(",", ":")))


@override_settings(ENABLE_PLAYWRIGHT_TESTS=True)
class ProductStepperE2E(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls) -> None:  # pragma: no cover - setup
        super().setUpClass()
        if sync_playwright is None:
            raise unittest.SkipTest("Playwright non installé (pip install playwright && playwright install)")

    def test_product_stepper_end_to_end(self) -> None:
        console_errors = []
        sign_payload = {}
        collect_payload = {}

        with sync_playwright() as pw:  # pragma: no cover - E2E
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(ignore_https_errors=True)
            context.add_cookies([
                {
                    "name": getattr(settings, "CONSENT_COOKIE_NAME", "consent"),
                    "value": "yes",
                    "url": self.live_server_url,
                }
            ])
            page = context.new_page()

            def _console(msg):
                if msg.type() == "error":
                    console_errors.append(msg.text())
            page.on("console", _console)

            def _route(route):
                req = route.request
                if req.method == "POST" and "/api/leads/sign" in req.url:
                    try:
                        sign_payload.update(req.post_data_json)
                    except Exception:
                        pass
                if req.method == "POST" and "/api/leads/collect" in req.url:
                    try:
                        collect_payload.update(req.post_data_json)
                    except Exception:
                        pass
                route.continue_()

            page.route("**/*", _route)

            page.goto(f"{self.live_server_url}/produits/", wait_until="networkidle")
            page.wait_for_selector('[data-cmp="product"]', timeout=15000)

            has_stepper = page.query_selector("[data-form-stepper]") is not None
            has_shell = page.query_selector("[data-ff-root]") is not None
            self.assertTrue(has_stepper or has_shell, "Steppeur introuvable sur la page produit")

            step1 = page.query_selector('.step-pane[data-step="1"]') or page
            fullname = step1.query_selector('input[name="full_name"], input[name="fullname"], input[autocomplete="name"], input[type="text"]')
            if fullname:
                fullname.fill("Client Test")
            phone = step1.query_selector('input[inputmode="tel"], input[type="tel"], input[name*="phone"]')
            if phone:
                phone.fill("+212600000000")
                pattern = phone.get_attribute("pattern")
                if pattern:
                    self.assertFalse(pattern.startswith("/") and pattern.endswith("/v"), f"pattern HTML suspect: {pattern}")
            next_btn = step1.query_selector('[data-next]')
            self.assertIsNotNone(next_btn, "Bouton data-next absent étape 1")
            next_btn.click()

            page.wait_for_selector('.step-pane[data-step="2"]:not(.d-none)', timeout=15000)
            step2 = page.query_selector('.step-pane[data-step="2"]') or page
            addr = step2.query_selector('input[name*="address"], textarea[name*="address"]')
            if addr:
                addr.fill("Adresse test")
            qty = step2.query_selector('select[name*="quantity"], input[name*="quantity"]')
            if qty:
                try:
                    qty.select_option("1")
                except Exception:
                    qty.fill("1")
            offer = step2.query_selector('select[name*="offer"], input[name*="offer"]')
            if offer:
                try:
                    offer.select_option("std")
                except Exception:
                    offer.fill("std")

            submit_btn = step2.query_selector('[data-submit-final], [data-next]')
            self.assertIsNotNone(submit_btn, "Bouton final étape 2 introuvable")
            submit_btn.click()

            page.wait_for_selector('.step-pane[data-step="3"]:not(.d-none), [data-thank-you], .c-thanks', timeout=20000)

            if console_errors:
                raise AssertionError("Erreurs console\n- " + "\n- ".join(console_errors))

            signed = _canonical((sign_payload or {}).get("payload"))
            collected = _canonical(collect_payload)
            if signed != collected:
                diffs = []
                for key in sorted(set(signed.keys()) | set(collected.keys())):
                    if json.dumps(signed.get(key), sort_keys=True) != json.dumps(collected.get(key), sort_keys=True):
                        diffs.append(f"{key}: sign={signed.get(key)!r} collect={collected.get(key)!r}")
                raise AssertionError("Payload /sign != /collect:\n" + "\n".join(diffs))

            context.close()
            browser.close()
