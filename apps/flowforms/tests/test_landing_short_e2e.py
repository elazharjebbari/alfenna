import json
import os
import pathlib
import uuid
from datetime import datetime

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.urls import Resolver404, resolve

from apps.leads.models import Lead, LeadSubmissionLog

from ._e2e_reporter import Reporter

PRODUCT_URL = "/flows/landing/"
PROGRESS_PATH = "/api/leads/progress/"
COLLECT_DEFAULT = "/api/leads/collect/"


@override_settings(ALLOWED_HOSTS=["*"])
class LandingShortE2E(StaticLiveServerTestCase):
    host = "127.0.0.1"

    def setUp(self):
        try:
            resolve(PRODUCT_URL)
        except Resolver404:
            self.skipTest(f"Route {PRODUCT_URL} introuvable (ajoute flowforms:landing-short).")

    # -------- helpers --------
    def _artifacts_dir(self) -> pathlib.Path:
        base = pathlib.Path.cwd() / "artifacts" / "flowforms_e2e"
        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        key = uuid.uuid4().hex[:6]
        target = base / f"{stamp}_{key}"
        target.mkdir(parents=True, exist_ok=True)
        return target

    def _wait_runtime_ready(self, page, reporter: Reporter):
        page.wait_for_selector('form[data-ff-root]', timeout=15000)
        reporter.note("root ready")
        page.wait_for_selector('script[data-ff-config]', state="attached", timeout=10000)
        reporter.note("config attached")
        page.wait_for_function(
            "() => !!window.fetch && !!document.querySelector('[data-ff-step] [data-ff-next]')",
            timeout=15000,
        )
        reporter.note("runtime ready")

    # -------- test body --------
    def test_landing_short_end_to_end(self):
        from playwright.sync_api import TimeoutError as PWTimeout
        from playwright.sync_api import sync_playwright

        reporter = Reporter(self._artifacts_dir())

        email = f"e2e.landing+{uuid.uuid4().hex[:6]}@example.com"
        headless = os.environ.get("HEADLESS", "1") not in {"0", "false", "False"}
        want_video = os.environ.get("VIDEO", "0") in {"1", "true", "True"}

        reporter.note("env", HEADLESS=headless, VIDEO=want_video, URL=PRODUCT_URL, email=email)

        with sync_playwright() as playwright:
            launch_kw = {"headless": headless}
            browser = playwright.chromium.launch(**launch_kw)
            context_kw = {}
            if want_video:
                context_kw["record_video_dir"] = str(reporter.videos_dir)
            context = browser.new_context(**context_kw)
            page = context.new_page()

            page.on(
                "console",
                lambda msg: reporter.log_console(
                    msg.type, msg.text, [arg.json_value() for arg in msg.args] if msg.args else None
                ),
            )
            page.on("request", reporter.log_request)
            page.on("response", reporter.log_response)

            def capture_progress(route):
                request = route.request
                if PROGRESS_PATH in request.url and request.method == "POST":
                    reporter.note("capture progress", url=request.url)
                    reporter.data["progress_calls"].append(
                        {
                            "url": request.url,
                            "headers": dict(request.headers),
                            "post_data": request.post_data or "",
                        }
                    )
                route.continue_()

            page.route(f"**{PROGRESS_PATH}**", capture_progress)

            with reporter.step("NAVIGATE"):
                page.goto(self.live_server_url + PRODUCT_URL, wait_until="networkidle")
                reporter.screenshot(page, "01_landing")
                self._wait_runtime_ready(page, reporter)

            with reporter.step("READ CONFIG"):
                conf_text = page.eval_on_selector(
                    "script[data-ff-config]",
                    "el => el ? el.textContent || '' : ''",
                ) or "{}"
                try:
                    cfg = json.loads(conf_text)
                except Exception:
                    cfg = {}
                    reporter.warn("ff-config JSON invalide")
                reporter.data["config"] = cfg
                reporter.note(
                    "ff-config parsed",
                    endpoint=cfg.get("endpoint_url") or COLLECT_DEFAULT,
                    steps=list((cfg.get("progress_steps") or {}).keys()),
                )

            def fill(selector, fallback, value, label):
                try:
                    page.locator(selector).wait_for(state="visible", timeout=1200)
                    page.fill(selector, value)
                    reporter.note("fill", field=label, selector=selector, value=value)
                except PWTimeout:
                    page.fill(fallback, value)
                    reporter.note("fill fallback", field=label, selector=fallback, value=value)
                except Exception as exc:
                    reporter.warn("fill failed", field=label, selector=selector, exc=str(exc))

            with reporter.step("STEP1"):
                fill("#ff-fullname", 'input[name="full_name"]', "E2E Landing", "full_name")
                fill("#ff-phone", 'input[name="phone"]', "0612345678", "phone")
                fill("#ff-city", 'input[name="city"]', "Rabat", "city")
                with page.expect_response(
                    lambda res: res.url.endswith(PROGRESS_PATH) and res.request.method == "POST"
                ) as progress_step1:
                    page.click('[data-ff-step="1"] [data-ff-next]')
                reporter.screenshot(page, "02_after_step1")
                reporter.log_response(progress_step1.value)

            with reporter.step("STEP2"):
                page.wait_for_selector('[data-ff-step="2"]:not(.d-none)', timeout=10000)
                try:
                    page.click('label.af-card-radio[data-id="duo"]', force=True)
                    reporter.note("pack chosen", code="duo")
                except Exception:
                    page.click('label.af-card-radio', force=True)
                    reporter.note("pack chosen fallback")
                page.evaluate("() => window.ffSyncPackFields && window.ffSyncPackFields()")
                hidden_value = page.eval_on_selector('[data-ff-pack-slug]', "el => el ? el.value : ''")
                reporter.note("hidden pack_slug", value=hidden_value)
                try:
                    page.check("#af-bump-optin", force=True)
                    reporter.note("bump checked")
                except Exception:
                    reporter.note("bump unavailable")
                with page.expect_response(
                    lambda res: res.url.endswith(PROGRESS_PATH) and res.request.method == "POST"
                ) as progress_step2:
                    page.click('[data-ff-step="2"] [data-ff-next]')
                reporter.screenshot(page, "03_after_step2")
                reporter.log_response(progress_step2.value)
                if reporter.data["progress_calls"]:
                    body = reporter.data["progress_calls"][-1].get("post_data") or ""
                    if '"pack_slug"' not in body:
                        reporter.warn("progress step2 sans pack_slug", body=body)

            with reporter.step("STEP3"):
                page.wait_for_selector('[data-ff-step="3"]:not(.d-none)', timeout=10000)
                try:
                    page.click('section[data-ff-step="3"] .af-pay-option[data-mode="cod"]')
                    reporter.note("payment set", mode="cod")
                except Exception:
                    reporter.note("payment default kept")
                try:
                    page.fill("#ff-email", email)
                except Exception:
                    reporter.warn("email field absent")

                endpoint_url = reporter.data["config"].get("endpoint_url") or COLLECT_DEFAULT
                with page.expect_response(
                    lambda res: res.url.endswith(endpoint_url) and res.request.method == "POST"
                ) as submit_response:
                    page.click('[data-ff-step="3"] [data-ff-submit]')
                reporter.screenshot(page, "04_after_submit")
                reporter.log_response(submit_response.value)
                try:
                    page.wait_for_selector('[data-ff-step="4"][data-thank-you]:not(.d-none)', timeout=10000)
                    reporter.note("thank-you visible")
                    reporter.screenshot(page, "05_thank_you")
                except Exception as exc:
                    reporter.warn("thank-you not visible", exc=str(exc))

            context.close()
            browser.close()

        with reporter.step("DB"):
            lead = Lead.objects.filter(form_kind="checkout_intent", email=email).order_by("-id").first()
            if not lead:
                reporter.error("Lead non trouvé", email=email)
                self.fail("Lead non créé")
            reporter.data["db"]["lead_id"] = lead.id
            reporter.data["db"]["pack_slug"] = getattr(lead, "pack_slug", "")
            reporter.data["db"]["context"] = lead.context or {}
            if reporter.data["db"]["pack_slug"] not in {"duo", "solo"}:
                reporter.warn("pack_slug inattendu", found=reporter.data["db"]["pack_slug"])

            log = LeadSubmissionLog.objects.filter(lead=lead).order_by("-created_at").first()
            if log:
                payload = log.payload or {}
                reporter.data["db"]["final_payload"] = payload
                pack_candidate = payload.get("pack_slug") or payload.get("offer_key")
                if pack_candidate not in {"duo", "solo"}:
                    reporter.warn("payload final sans pack attendu", payload=payload)
            else:
                reporter.warn("LeadSubmissionLog absent")

        reporter.finalize()

        self.assertIsNotNone(reporter.data["db"].get("lead_id"))
        self.assertGreaterEqual(len(reporter.data["progress_calls"]), 2)
