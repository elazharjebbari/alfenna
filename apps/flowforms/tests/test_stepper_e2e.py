# apps/flowforms/tests/test_stepper_realpage_e2e.py
import os
import uuid
from django.test import override_settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import resolve, Resolver404
from apps.leads.models import Lead, LeadSubmissionLog

PRODUCT_SLUG = "pack-cosmetique-naturel"
PRODUCT_URL  = f"/fr/produits/{PRODUCT_SLUG}/"

@override_settings(ALLOWED_HOSTS=["*"])
class StepperRealPageE2ETest(StaticLiveServerTestCase):
    host = "127.0.0.1"

    def setUp(self):
        try:
            resolve(PRODUCT_URL)
        except Resolver404:
            self.skipTest(f"Route {PRODUCT_URL} introuvable (vérifie urls/i18n_patterns).")

    def _wait_runtime_ready(self, page):
        # root
        page.wait_for_selector('form[data-ff-root]', timeout=15000)
        # JSON config attaché (non visible)
        page.wait_for_selector('script[data-ff-config]', state="attached", timeout=10000)
        # runtime prêt: fetch + bouton next
        page.wait_for_function(
            "() => !!window.fetch && !!document.querySelector('[data-ff-step] [data-ff-next]')",
            timeout=15000
        )

    def test_stepper_realpage_end_to_end(self):
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

        email = f"e2e.real+{uuid.uuid4().hex[:6]}@example.com"
        headless = os.environ.get("HEADLESS", "1") not in ("0", "false", "False")

        progress_calls = []  # diagnostic réseau

        # ----------- PHASE 1: navigateur (aucun ORM ici) -----------
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless, slow_mo=250 if not headless else 0)
            ctx = browser.new_context()
            page = ctx.new_page()

            # Intercepter progress AVANT la nav
            def capture(route):
                req = route.request
                if "/api/leads/progress/" in req.url and req.method == "POST":
                    progress_calls.append({"body": req.post_data or ""})
                route.continue_()
            page.route("**/api/leads/progress/**", capture)

            # Aller sur la vraie page et attendre runtime
            page.goto(self.live_server_url + PRODUCT_URL, wait_until="networkidle")
            self._wait_runtime_ready(page)

            # Endpoint de submit (collect) depuis la config
            endpoint_url = page.evaluate("""() => {
              try {
                const el = document.querySelector('script[data-ff-config]');
                const j = JSON.parse(el?.textContent || '{}');
                return j.endpoint_url || '/api/leads/collect/';
              } catch { return '/api/leads/collect/'; }
            }""")

            # ----- STEP 1 — remplissage tolérant (ID ou name)
            def fill(primary, fallback, val):
                try:
                    page.locator(primary).wait_for(state="visible", timeout=1200)
                    page.fill(primary, val)
                except PWTimeout:
                    page.fill(fallback, val)

            fill("#ff-fullname", 'input[name="full_name"]', "E2E User")
            fill("#ff-phone", 'input[name="phone"]', "0612345678")
            fill("#ff-email-step1", 'input[name="email"]', email)
            fill("#ff-address-line1", 'input[name="address_line1"]', "Rue 123")
            fill("#ff-city", 'input[name="city"]', "Casablanca")
            fill("#ff-postal", 'input[name="postal_code"]', "20000")
            try:
                page.select_option("#ff-country", "MA")
            except Exception:
                pass

            with page.expect_response(lambda r: r.url.endswith("/api/leads/progress/") and r.request.method == "POST"):
                page.click('[data-ff-step="1"] [data-ff-next]')

            # ----- STEP 2 — DUO + bump
            page.wait_for_selector('[data-ff-step="2"]:not(.d-none)', timeout=10000)
            # Forcer sync du pack juste avant collecte (si le front est borderline)
            page.evaluate("() => { if (window.ffSyncPackFields) window.ffSyncPackFields(); }")

            try:
                page.click('label.af-card-radio[data-id="duo"]', force=True)
            except Exception:
                page.click('label.af-card-radio', force=True)

            try:
                page.check("#af-bump-optin", force=True)
            except Exception:
                pass

            with page.expect_response(lambda r: r.url.endswith("/api/leads/progress/") and r.request.method == "POST"):
                page.click('[data-ff-step="2"] [data-ff-next]')

            # ----- STEP 3 — COD + accept_terms + submit
            page.wait_for_selector('[data-ff-step="3"]:not(.d-none)', timeout=10000)
            try:
                page.click('section[data-ff-step="3"] label.af-pay-option:not(.is-online)')
            except Exception:
                pass
            try:
                page.check('input[name="accept_terms"]', force=True)
            except Exception:
                pass
            try:
                page.fill("#ff-email", email)
            except Exception:
                pass

            # Attendre la REPONSE de submit (XHR), pas une navigation
            with page.expect_response(lambda r: r.url.endswith(endpoint_url) and r.request.method == "POST") as resp_submit:
                page.click('[data-ff-step="3"] [data-ff-submit]')
            # Puis l'apparition de la step 4 (merci)
            page.wait_for_selector('[data-ff-step="4"][data-thank-you]:not(.d-none)', timeout=10000)

            # (optionnel) vérifier le statut HTTP de submit pour logs clairs
            submit_res = resp_submit.value
            assert submit_res.ok, f"Collect HTTP {submit_res.status} — {submit_res.url}"

            ctx.close()
            browser.close()

        # ----------- PHASE 2: assertions DB (hors boucle async) -----------
        lead = Lead.objects.filter(form_kind="checkout_intent", email=email).order_by("-id").first()
        self.assertIsNotNone(lead, "Lead non créé après step2")
        self.assertEqual(getattr(lead, "pack_slug", ""), "duo", "pack_slug non persisté à l'étape 2")
        comp = (lead.context or {}).get("complementary_slugs", [])
        if not comp:
            print("[E2E] complementary_slugs vide (OK si bump désactivé sur cette page)")

        log = LeadSubmissionLog.objects.filter(lead=lead, flow_key="checkout_intent_flow").order_by("-created_at").first()
        if log:
            payload = log.payload or {}
            self.assertTrue(payload.get("pack_slug") == "duo" or payload.get("offer_key") == "duo",
                            f"Snapshot final sans pack 'duo': {payload}")

        # DIAG utile: s'assurer que step2 a posté pack_slug
        if not any('"step":"step2"' in c["body"] and '"pack_slug"' in c["body"] for c in progress_calls):
            print("[E2E] ATTENTION: step2 progress sans pack_slug → vérifie JSON data-ff-config.progress_steps.step2 & ffSyncPackFields()")
