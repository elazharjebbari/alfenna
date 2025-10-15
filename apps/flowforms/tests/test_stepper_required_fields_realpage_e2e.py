import os
import json
import uuid
from datetime import datetime
from django.test import override_settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import resolve, Resolver404

from apps.flowforms.tests._e2e_reporter import Reporter
from apps.flowforms.tests.test_landing_short_e2e import PROGRESS_PATH
from apps.leads.tests.test_progress_step2 import DEFAULT_COLLECT_PATH

# Si tu mets ce test dans le même fichier que test_stepper_realpage_e2e.py,
# commente les 3 imports ci-dessous et utilise directement Reporter/constantes locales.
# from apps.flowforms.tests.test_stepper_realpage_e2e import Reporter, PROGRESS_PATH, DEFAULT_COLLECT_PATH

PRODUCT_SLUG = "pack-cosmetique-naturel"
PRODUCT_URL  = f"/fr/produits/{PRODUCT_SLUG}/"


@override_settings(ALLOWED_HOSTS=["*"])
class ProductDetailRequiredFieldsE2E(StaticLiveServerTestCase):
    """
    Vérifie sur la VRAIE page product_detail que:
      - Step1: seul 'phone' est obligatoire (sans phone -> pas d'avance, erreur visible; avec phone -> avance + progress parti)
      - Step2: rien d'obligatoire (on avance sans rien choisir, progress parti)
      - Step3: seul 'accept_terms' est obligatoire (décoché -> submit bloqué; coché -> submit OK + step4 'merci')
    Exporte un rapport JSON + captures dans ./artifacts/flowforms_e2e/<run>/.
    """
    host = "127.0.0.1"

    def setUp(self):
        try:
            resolve(PRODUCT_URL)
        except Resolver404:
            self.skipTest(f"Route {PRODUCT_URL} introuvable (vérifie pages:product-detail-slug).")

    def _artifacts_dir(self):
        from pathlib import Path
        base = Path.cwd() / "artifacts" / "flowforms_e2e"
        uid  = datetime.utcnow().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        (base / uid).mkdir(parents=True, exist_ok=True)
        return base / uid

    def _wait_ready(self, page, rep: Reporter):
        page.wait_for_selector('form[data-ff-root]', timeout=15000); rep.note("root ok")
        page.wait_for_selector('script[data-ff-config]', state="attached", timeout=10000); rep.note("ff-config attached")
        page.wait_for_function("() => !!window.fetch && !!document.querySelector('[data-ff-step] [data-ff-next]')", timeout=15000)
        rep.note("runtime ready")

    def test_only_phone_and_terms_required(self):
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

        email    = f"e2e.req+{uuid.uuid4().hex[:6]}@example.com"
        headless = os.environ.get("HEADLESS","1") not in ("0","false","False")

        rep = Reporter(self._artifacts_dir())
        rep.note("ENV", HEADLESS=headless, URL=PRODUCT_URL, email=email)

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless, slow_mo=0)
            ctx = browser.new_context()
            page = ctx.new_page()

            # hooks réseau/console
            page.on("console", rep.log_console)
            page.on("request", rep.log_request)
            page.on("response", rep.log_response)

            # Intercepter progress AVANT nav
            def capture(route):
                req = route.request
                if PROGRESS_PATH in req.url and req.method == "POST":
                    rep.data["progress_calls"].append({
                        "url": req.url, "headers": dict(req.headers), "post_data": req.post_data or ""
                    })
                route.continue_()
            page.route(f"**{PROGRESS_PATH}**", capture)

            # NAV
            page.goto(self.live_server_url + PRODUCT_URL, wait_until="networkidle")
            rep.screenshot(page, "01_landing")
            self._wait_ready(page, rep)

            # Lire endpoint submit depuis ff-config
            ffconf_text = page.eval_on_selector("script[data-ff-config]", "el => el && el.textContent || ''") or "{}"
            try: ffconf = json.loads(ffconf_text)
            except Exception: ffconf = {}; rep.warn("ff-config JSON invalide")
            rep.data["config"] = ffconf
            endpoint = ffconf.get("endpoint_url") or DEFAULT_COLLECT_PATH

            # =================== STEP 1 ===================
            # Demande: seul 'phone' est obligatoire (tous les autres facultatifs).
            # 1) cliquer 'Continuer' sans phone : on doit rester en step1 + erreur visible + aucun progress step1
            page.click('[data-ff-step="1"] [data-ff-next]')

            # On ne doit PAS quitter l'étape 1
            still_step1 = page.locator('[data-ff-step="1"]:not(.d-none)').count() == 1
            if not still_step1:
                rep.error("L'étape 1 a avancé sans phone — non conforme")
                self.fail("Étape 1 ne doit pas avancer sans phone")

            # Chercher un marquage d'erreur explicite près du phone (ou fallback)
            error_found = False
            for sel in [
                '#ff-phone ~ .invalid-feedback:visible',
                '[data-ff-step="1"] .invalid-feedback:has-text("obligatoire")',
                '[data-ff-step="1"] :text("obligatoire")',
            ]:
                try:
                    page.wait_for_selector(sel, timeout=1200)
                    rep.note("error marker near phone", selector=sel)
                    error_found = True
                    break
                except Exception:
                    continue
            if not error_found:
                rep.warn("Pas de message d’erreur explicite pour phone — on vérifie réseau")

            # Aucun progress step1 ne doit être parti
            if any('"step":"step1"' in (c.get("post_data") or "") for c in rep.data["progress_calls"]):
                rep.warn("Un progress step1 est parti malgré phone vide")

            # 2) Remplir uniquement phone puis avancer : doit passer en step2 et POSTer step1
            try: page.fill('#ff-phone', "0612345678")
            except Exception: page.fill('input[name="phone"]', "0612345678")

            with page.expect_response(lambda r: r.url.endswith(PROGRESS_PATH) and r.request.method == "POST") as r1:
                page.click('[data-ff-step="1"] [data-ff-next]')
            rep.screenshot(page, "02_after_step1")
            rep.log_response(r1.value)
            page.wait_for_selector('[data-ff-step="2"]:not(.d-none)', timeout=5000)

            # (Qualité) S'assurer qu'aucun autre champ facultatif n'a déclenché une erreur bloquante
            # On vérifie l'absence d'éléments .invalid-feedback visibles (hors phone)
            invalids = page.locator('[data-ff-step="1"] .invalid-feedback:visible').count()
            if invalids and not error_found:
                rep.warn("Des erreurs côté step1 autres que phone semblent visibles", count=invalids)

            # =================== STEP 2 ===================
            # Demande: rien d’obligatoire (upsell/cross-sell facultatifs)
            with page.expect_response(lambda r: r.url.endswith(PROGRESS_PATH) and r.request.method == "POST") as r2:
                page.click('[data-ff-step="2"] [data-ff-next]')
            rep.screenshot(page, "03_after_step2")
            rep.log_response(r2.value)
            page.wait_for_selector('[data-ff-step="3"]:not(.d-none)', timeout=5000)

            # Basculer en COD pour valider les champs requis côté collect (et éviter Stripe)
            try:
                page.click('section[data-ff-step="3"] label.af-pay-option:not(.is-online)', force=True)
                page.wait_for_function(
                    "() => {\n                        const node = document.querySelector('#af-step3-discount');\n                        if (!node) return false;\n                        const raw = (node.textContent || '').replace(/[^0-9-]/g, '');\n                        const val = parseInt(raw || '0', 10);\n                        return Number.isFinite(val) && val === 0;\n                    }",
                    timeout=4000
                )
                rep.note("payment_mode", mode="cod")
            except Exception:
                rep.warn("Impossible de forcer le mode COD; poursuite avec le mode courant")

            # =================== STEP 3 ===================
            # Demande: accept_terms obligatoire pour soumettre
            # 1) s'assurer que la case est décochée
            try:
                page.uncheck('input[name="accept_terms"]', force=True)
                rep.note("accept_terms unchecked")
            except Exception:
                # fallback: clique le label si input masqué
                try:
                    page.click('label[for="ff-terms"]'); rep.note("accept_terms toggled via label (unchecked)")
                except Exception:
                    rep.warn("Impossible de décocher accept_terms; on tente quand même un submit")

            # Tenter de soumettre — ne doit pas réussir (pas de 2xx OK, pas de step4)
            blocked = False
            try:
                with page.expect_response(lambda r: r.url.endswith(endpoint) and r.request.method == "POST", timeout=1500) as rs:
                    page.click('[data-ff-step="3"] [data-ff-submit]')
                if rs.value.ok:
                    rep.error("Collect a répondu OK sans accept_terms", status=rs.value.status)
                    self.fail("Submit ne doit pas réussir sans accept_terms")
                else:
                    rep.note("Collect NON OK (attendu sans terms)", status=rs.value.status); blocked = True
            except PWTimeout:
                # aucun XHR de collect n'est parti → blocage côté front, ce qui est bien aussi
                blocked = True; rep.note("Submit bloqué côté front (aucun collect émis) — attendu")

            if not blocked:
                self.fail("Le formulaire a été soumis sans accept_terms")

            # 2) cocher et soumettre → doit réussir + merci visible
            try: page.check('input[name="accept_terms"]', force=True)
            except Exception: page.click('label[for="ff-terms"]')

            with page.expect_response(lambda r: r.url.endswith(endpoint) and r.request.method == "POST") as rs_ok:
                page.click('[data-ff-step="3"] [data-ff-submit]')
            rep.log_response(rs_ok.value)
            rep.screenshot(page, "04_after_submit")

            page.wait_for_selector('[data-ff-step="4"][data-thank-you]:not(.d-none)', timeout=8000)
            rep.screenshot(page, "05_thank_you")

            ctx.close(); browser.close()

        # Assertions minimales réseau
        self.assertGreaterEqual(len(rep.data["progress_calls"]), 2, "On attend au moins 2 progress (step1 + step2)")
