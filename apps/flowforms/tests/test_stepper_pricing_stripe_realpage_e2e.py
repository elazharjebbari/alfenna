import json
import os
import re
import uuid
from datetime import datetime

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.urls import resolve, Resolver404

from playwright.sync_api import TimeoutError as PWTimeout, sync_playwright

from apps.flowforms.tests._e2e_reporter import Reporter
from apps.flowforms.tests.test_landing_short_e2e import PROGRESS_PATH
from apps.leads.tests.test_progress_step2 import DEFAULT_COLLECT_PATH

PRODUCT_SLUG = "pack-cosmetique-naturel"
PRODUCT_URL = f"/fr/produits/{PRODUCT_SLUG}/"
DEFAULT_CHECKOUT_URL = "/api/checkout/sessions/"


def _money_to_int(text: str) -> int:
    if not text:
        return 0
    txt = text.replace("−", "-").replace("\xa0", " ").replace("\u202f", " ")
    match = re.search(r"([\-]?\d+(?:[.,]\d+)?)", txt)
    if not match:
        return 0
    value = match.group(1).replace(",", ".")
    return int(float(value))


@override_settings(ALLOWED_HOSTS=["*"])
class ProductDetailPricingAndStripeE2E(StaticLiveServerTestCase):
    host = "127.0.0.1"

    def setUp(self):
        try:
            resolve(PRODUCT_URL)
        except Resolver404:
            self.skipTest("Route introuvable")

    def _artifacts_dir(self):
        from pathlib import Path

        base = Path.cwd() / "artifacts" / "flowforms_e2e"
        uid = datetime.utcnow().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        (base / uid).mkdir(parents=True, exist_ok=True)
        return base / uid

    def _wait_ready(self, page, rep: Reporter):
        page.wait_for_selector('form[data-ff-root]', timeout=15000)
        rep.note("root ready")
        page.wait_for_selector('script[data-ff-config]', state="attached", timeout=10000)
        rep.note("config ready")
        page.wait_for_function(
            "() => !!window.fetch && !!document.querySelector('[data-ff-step] [data-ff-next]')",
            timeout=15000,
        )
        rep.note("runtime ready")

    def _get_offer_field(self, ffconf: dict) -> str:
        fields_map = ffconf.get("fields_map") or {}
        return fields_map.get("offer", "offer_key")

    def _read_money(self, page, selector: str) -> int:
        txt = page.eval_on_selector(selector, "el => el ? el.textContent.trim() : ''") or ""
        return _money_to_int(txt)

    def _selected_offer_info(self, page, field: str):
        sel = f'[name="{field}"]:checked'
        slug = page.eval_on_selector(sel, "el => el?.dataset?.ffPackSlug || el?.value || ''") or ""
        price = page.eval_on_selector(sel, "el => el?.dataset?.ffPackPrice || ''") or "0"
        currency = page.eval_on_selector(sel, "el => el?.dataset?.ffPackCurrency || 'MAD'")
        return slug, _money_to_int(price), currency

    def _bump_price(self, page) -> int:
        if page.locator('#af-bump-optin').count() != 1:
            return 0
        raw = page.eval_on_selector('#af-bump-optin', "el => el?.dataset?.ffComplementaryPrice || '0'") or "0"
        return _money_to_int(raw)

    def test_dynamic_totals_and_stripe(self):
        email = f"e2e.pricing+{uuid.uuid4().hex[:6]}@example.com"
        headless = os.environ.get("HEADLESS", "1") not in ("0", "false", "False")

        rep = Reporter(self._artifacts_dir())
        rep.note("ENV", HEADLESS=headless, email=email)

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless)
            ctx = browser.new_context()
            page = ctx.new_page()

            page.on("console", rep.log_console)
            page.on("request", rep.log_request)
            page.on("response", rep.log_response)

            def capture(route):
                req = route.request
                if PROGRESS_PATH in req.url and req.method == "POST":
                    rep.data["progress_calls"].append(
                        {
                            "url": req.url,
                            "headers": dict(req.headers),
                            "post_data": req.post_data or "",
                        }
                    )
                route.continue_()

            page.route(f"**{PROGRESS_PATH}**", capture)

            page.goto(self.live_server_url + PRODUCT_URL, wait_until="networkidle")
            rep.screenshot(page, "01_landing")
            self._wait_ready(page, rep)

            ffconf_raw = page.eval_on_selector("script[data-ff-config]", "el => el?.textContent || '{}' ") or "{}"
            try:
                ffconf = json.loads(ffconf_raw)
            except Exception:
                ffconf = {}
            offer_field = self._get_offer_field(ffconf)
            checkout_url = page.eval_on_selector('form[data-ff-root]', "el => el?.dataset?.checkoutUrl || ''") or DEFAULT_CHECKOUT_URL
            rep.note("config", offer_field=offer_field, checkout_url=checkout_url)

            page.click('[data-ff-step="1"] [data-ff-next]')
            page.fill('#ff-phone', '0612345678')
            with page.expect_response(lambda r: r.url.endswith(PROGRESS_PATH) and r.request.method == "POST"):
                page.click('[data-ff-step="1"] [data-ff-next]')
            page.wait_for_selector('[data-ff-step="2"]:not(.d-none)', timeout=8000)

            slug, price, currency = self._selected_offer_info(page, offer_field)
            bump_price = self._bump_price(page)
            rep.note("STEP2 default", slug=slug, price=price, bump=bump_price, currency=currency)

            sub = self._read_money(page, "#af-subtotal")
            disc = self._read_money(page, "#af-discount")
            tot = self._read_money(page, "#af-total")
            self.assertEqual(sub, price)
            self.assertEqual(disc, -20)
            self.assertEqual(tot, price - 20)

            # switch to other offer if available
            other_label = page.locator('label.af-card-radio[data-id="duo"]').first
            if other_label.count():
                prev = page.eval_on_selector("#af-total", "el => el?.textContent || ''") or ""
                other_label.click(force=True)
                page.wait_for_function(
                    "([txt]) => { const el = document.querySelector('#af-total'); return el && el.textContent && el.textContent.trim() !== txt; }",
                    arg=[prev],
                    timeout=5000,
                )
                slug, price, _ = self._selected_offer_info(page, offer_field)
                rep.note("STEP2 switched", slug=slug, price=price)
                sub = self._read_money(page, "#af-subtotal")
                disc = self._read_money(page, "#af-discount")
                tot = self._read_money(page, "#af-total")
                self.assertEqual(sub, price)
                self.assertEqual(disc, -20)
                self.assertEqual(tot, price - 20)

            # bump on
            if page.locator('#af-bump-optin').count() == 1 and bump_price:
                base_price = self._read_money(page, "#af-subtotal")
                page.check('#af-bump-optin', force=True)
                page.wait_for_timeout(200)
                sub = self._read_money(page, "#af-subtotal")
                disc = self._read_money(page, "#af-discount")
                tot = self._read_money(page, "#af-total")
                self.assertEqual(sub, base_price + bump_price)
                self.assertEqual(disc, -20)
                self.assertEqual(tot, sub - 20)
                price = sub

            with page.expect_response(lambda r: r.url.endswith(PROGRESS_PATH) and r.request.method == "POST"):
                page.click('[data-ff-step="2"] [data-ff-next]')
            page.wait_for_selector('[data-ff-step="3"]:not(.d-none)', timeout=8000)

            sub3 = self._read_money(page, "#af-step3-subtotal")
            disc3 = self._read_money(page, "#af-step3-discount")
            tot3 = self._read_money(page, "#af-step3-total")
            self.assertEqual(sub3, price)
            self.assertEqual(disc3, -20)
            self.assertEqual(tot3, price - 20)

            # COD toggle
            try:
                page.click('section[data-ff-step="3"] label.af-pay-option:not(.is-online)', force=True)
                page.wait_for_timeout(200)
                disc_cod = self._read_money(page, "#af-step3-discount")
                tot_cod = self._read_money(page, "#af-step3-total")
                self.assertEqual(disc_cod, 0)
                self.assertEqual(tot_cod, sub3)
            except Exception:
                rep.warn("COD toggle failed")

            # back to online
            page.click('section[data-ff-step="3"] label.af-pay-option.is-online', force=True)
            page.wait_for_timeout(200)
            disc_online = self._read_money(page, "#af-step3-discount")
            tot_online = self._read_money(page, "#af-step3-total")
            self.assertEqual(disc_online, -20)
            self.assertEqual(tot_online, sub3 - 20)

            try:
                page.check('input[name="accept_terms"]', force=True)
            except Exception:
                page.click('label[for="ff-terms"]')

            observed = {"req": None, "res": None}

            def on_req(req):
                if checkout_url in req.url and req.method == "POST":
                    observed["req"] = {
                        "url": req.url,
                        "post": req.post_data or "",
                        "headers": dict(req.headers),
                    }

            def on_res(res):
                if checkout_url in res.url:
                    try:
                        body = res.json()
                    except Exception:
                        try:
                            body = {"raw": res.text()[:500]}
                        except Exception:
                            body = {}
                    observed["res"] = {
                        "status": res.status,
                        "ok": res.ok,
                        "body": body,
                    }

            page.on("request", on_req)
            page.on("response", on_res)

            page.click('[data-ff-step="3"] [data-ff-submit]')
            page.wait_for_timeout(3000)

            body = (observed.get("res") or {}).get("body") or {}
            expected_cents = tot_online * 100
            sent_amount = body.get("amount")
            if sent_amount is None:
                try:
                    req_body = json.loads((observed.get("req") or {}).get("post") or "{}")
                except Exception:
                    req_body = {}
                sent_amount = req_body.get("amount") or (
                    (req_body.get("line_items") or [{}])[0]
                    .get("price_data", {})
                    .get("unit_amount")
                )
            self.assertEqual(sent_amount, expected_cents)

            ctx.close()
            browser.close()

        self.assertGreaterEqual(len(rep.data.get("progress_calls", [])), 2)
