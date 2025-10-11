# apps/billing/tests/test_stepper_to_stripe_e2e.py
import os
import re
import hmac
import json
import time
import uuid
import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.urls import resolve, Resolver404

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# Reporter util déjà présent dans ton repo
from apps.flowforms.tests._e2e_reporter import Reporter  # artefacts/screens/videos + logs
# Modèles billing (selon ton codebook/projet)
from apps.billing.models import Order, Payment, PaymentLog, OrderStatus  # DB assertions


# ---- Cibles & endpoints
PRODUCT_SLUG = "pack-cosmetique-naturel"
PRODUCT_URL  = f"/fr/produits/{PRODUCT_SLUG}/"

PROGRESS_PATH        = "/api/leads/progress/"
DEFAULT_COLLECT_PATH = "/api/leads/collect/"
INTENT_CREATE_PATH   = "/billing/intent/create/"   # renvoie clientSecret, amount, currency, orderId (selon ton back)
STRIPE_WEBHOOK_PATH  = "/billing/webhook/"         # reçoit payment_intent.succeeded etc.


# ---------- petits utilitaires ----------
def _money_to_int(text: str) -> int:
    """lit '489 MAD' / '−20 MAD' -> int en MAD (centimes ignorés si absents)"""
    if not text:
        return 0
    txt = text.replace("−", "-").replace("\xa0", " ").replace("\u202f", " ").strip()
    m = re.search(r"([\-]?\d+(?:[.,]\d+)?)", txt)
    if not m:
        return 0
    val = m.group(1).replace(",", ".")
    return int(float(val))

def _now() -> int:
    return int(time.time())

def _sign_stripe_payload(secret: str, payload: str, ts: Optional[int] = None) -> str:
    """
    Stripe-Signature header : t=timestamp,v1=HMAC_SHA256(f"{t}.{payload}", secret)
    """
    ts = ts or _now()
    signed_payload = f"{ts}.{payload}".encode("utf-8")
    mac = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"

@dataclass
class AmountSnapshot:
    step: int
    subtotal: int
    discount: int
    total: int


@override_settings(ALLOWED_HOSTS=["*"])
class ProductDetailStripePaymentE2E(StaticLiveServerTestCase):
    """
    Stepper → paiement online (Elements/Checkout) → webhook (réel ou simulé) → DB OK.
    Exporte un rapport JSON + captures dans artifacts/flowforms_e2e/<run>/.
    """
    host = "127.0.0.1"

    # ---------- helpers ----------
    def _artifacts_dir(self) -> Path:
        base = Path.cwd() / "artifacts" / "flowforms_e2e"
        uid  = datetime.utcnow().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        path = base / uid
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _wait_ready(self, page, rep: Reporter):
        page.wait_for_selector('form[data-ff-root]', timeout=15000); rep.note("root ready")
        page.wait_for_selector('script[data-ff-config]', state="attached", timeout=10000); rep.note("ff-config attached")
        page.wait_for_function("() => !!window.fetch && !!document.querySelector('[data-ff-step] [data-ff-next]')", timeout=15000)
        rep.note("runtime ready")

    def _read_money(self, page, selector: str) -> int:
        txt = page.eval_on_selector(selector, "el => el ? el.textContent.trim() : ''") or ""
        return _money_to_int(txt)

    def _capture_step_amounts(self, page, step: int) -> AmountSnapshot:
        if step == 2:
            return AmountSnapshot(
                step=2,
                subtotal=self._read_money(page, "#af-subtotal"),
                discount=self._read_money(page, "#af-discount"),
                total=self._read_money(page, "#af-total"),
            )
        if step == 3:
            return AmountSnapshot(
                step=3,
                subtotal=self._read_money(page, "#af-step3-subtotal"),
                discount=self._read_money(page, "#af-step3-discount"),
                total=self._read_money(page, "#af-step3-total"),
            )
        raise AssertionError("step doit être 2 ou 3")

    def _extract_pi_from_client_secret(self, client_secret: str) -> Optional[str]:
        # client_secret format 'pi_XXXX_secret_YYYY' ou 'pi_xxx_yyy_secret_zzz' => on coupe à '_secret'
        if not client_secret:
            return None
        idx = client_secret.find("_secret")
        return client_secret[:idx] if idx > 0 else None

    def _post_stripe_webhook(self, ctx, rep: Reporter, pi_id: str, amount_cents: int, currency: str):
        """
        Simule le webhook Stripe payment_intent.succeeded avec signature valide.
        """
        secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
        if not secret:
            rep.warn("STRIPE_WEBHOOK_SECRET manquant — simulation webhook impossible")
            return False

        payload = json.dumps({
            "id": f"evt_{uuid.uuid4().hex[:14]}",
            "type": "payment_intent.succeeded",
            "data": {"object": {
                "id": pi_id,
                "object": "payment_intent",
                "status": "succeeded",
                "amount": int(amount_cents),
                "currency": (currency or "mad").lower(),
                "latest_charge": f"ch_{uuid.uuid4().hex[:14]}",
                "charges": {"data": []},
            }},
            "created": _now()
        }, separators=(",", ":"), ensure_ascii=False)
        sig = _sign_stripe_payload(secret, payload)

        url = self.live_server_url + STRIPE_WEBHOOK_PATH
        rep.note("POST webhook (simulé)", url=url, pi=pi_id, amount=amount_cents, currency=currency)
        resp = ctx.request.post(
            url,
            headers={"Stripe-Signature": sig, "Content-Type": "application/json"},
            data=payload.encode("utf-8"),
            timeout=10_000,
        )
        rep.note("webhook response", status=resp.status, ok=resp.ok)
        return resp.ok

    def setUp(self):
        try:
            resolve(PRODUCT_URL)
        except Resolver404:
            self.skipTest(f"Route {PRODUCT_URL} introuvable (product_detail).")

    # -------------- le test principal --------------
    def test_stepper_to_stripe_payment_and_webhook(self):
        email     = f"e2e.pay+{uuid.uuid4().hex[:6]}@example.com"
        headless  = os.environ.get("HEADLESS", "1") not in ("0", "false", "False")
        try_real  = os.environ.get("STRIPE_E2E_REAL", "0") in ("1", "true", "True")

        # IMPORTANT: on passe le **chemin** au Reporter, pas la fonction !
        rep = Reporter(self._artifacts_dir())
        rep.note("ENV", HEADLESS=headless, PRODUCT_URL=PRODUCT_URL, email=email, STRIPE_E2E_REAL=try_real)

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless)
            ctx = browser.new_context()
            page = ctx.new_page()

            # logs front/réseau → reporter
            page.on("console", rep.log_console)
            page.on("request", rep.log_request)
            page.on("response", rep.log_response)

            # capture progress
            def capture(route):
                req = route.request
                if PROGRESS_PATH in req.url and req.method == "POST":
                    rep.data["progress_calls"].append({
                        "url": req.url, "headers": dict(req.headers), "post_data": req.post_data or ""
                    })
                route.continue_()
            page.route(f"**{PROGRESS_PATH}**", capture)

            # Aller sur la page produit
            page.goto(self.live_server_url + PRODUCT_URL, wait_until="networkidle")
            rep.screenshot(page, "01_landing")
            self._wait_ready(page, rep)

            # STEP1 : phone only → next
            page.click('[data-ff-step="1"] [data-ff-next]')
            page.wait_for_selector('[data-ff-step="1"]:not(.d-none)', timeout=3000)  # on reste bloqué sans phone
            page.fill('#ff-phone', '0612345678')
            with page.expect_response(lambda r: r.url.endswith(PROGRESS_PATH) and r.request.method == "POST"):
                page.click('[data-ff-step="1"] [data-ff-next]')
            rep.screenshot(page, "02_after_step1")
            page.wait_for_selector('[data-ff-step="2"]:not(.d-none)', timeout=8000)

            # STEP2 : vérifier montants initiaux (remise online négative)
            snap2 = self._capture_step_amounts(page, 2)
            rep.note("STEP2 amounts", **snap2.__dict__)
            online_discount = snap2.discount  # ex. -20
            self.assertLessEqual(online_discount, 0, "La remise en ligne doit être ≤ 0 (ex: −20)")
            self.assertEqual(snap2.total, snap2.subtotal + online_discount)

            # cocher bump si présent (optionnel)
            if page.locator('#af-bump-optin').count():
                base = self._capture_step_amounts(page, 2)
                page.check('#af-bump-optin', force=True)
                page.wait_for_timeout(200)
                snap2b = self._capture_step_amounts(page, 2)
                rep.note("STEP2 after bump", **snap2b.__dict__)
                self.assertGreaterEqual(snap2b.subtotal, base.subtotal)
                self.assertEqual(snap2b.total, snap2b.subtotal + online_discount)
                snap2 = snap2b

            # Next → STEP3
            with page.expect_response(lambda r: r.url.endswith(PROGRESS_PATH) and r.request.method == "POST"):
                page.click('[data-ff-step="2"] [data-ff-next]')
            rep.screenshot(page, "03_after_step2")
            page.wait_for_selector('[data-ff-step="3"]:not(.d-none)', timeout=8000)

            # STEP3 : forcer online
            try:
                page.click('section[data-ff-step="3"] label.af-pay-option.is-online', force=True)
            except Exception:
                pass
            page.wait_for_timeout(150)
            snap3 = self._capture_step_amounts(page, 3)
            rep.note("STEP3 online amounts", **snap3.__dict__)
            self.assertEqual(snap3.discount, online_discount)
            self.assertEqual(snap3.total, snap3.subtotal + online_discount)

            # accepter CGU
            try:
                page.check('input[name="accept_terms"]', force=True)
            except Exception:
                page.click('label[for="ff-terms"]')

            # ——— intercept création d’intent/séance checkout
            observed: Dict[str, Any] = {"intent": None, "checkout": None}
            def on_res(res):
                url = res.url or ""
                if url.endswith(INTENT_CREATE_PATH):
                    try:
                        js = res.json()
                    except Exception:
                        js = {}
                    observed["intent"] = {"status": res.status, "ok": res.ok, "json": js}
                if "/api/checkout/sessions/" in url:
                    try:
                        js = res.json()
                    except Exception:
                        js = {}
                    observed["checkout"] = {"status": res.status, "ok": res.ok, "json": js}
            page.on("response", on_res)

            # submit → intent + (payment element ou checkout)
            page.click('[data-ff-step="3"] [data-ff-submit]')
            rep.screenshot(page, "04_after_submit_click")
            page.wait_for_timeout(800)  # laisse le XHR partir

            # Vérif payload d’intent (montant attendu)
            intent = observed.get("intent") or {}
            js = intent.get("json") or {}
            client_secret = js.get("clientSecret") or js.get("client_secret") or ""
            amount_cents = js.get("amount")
            currency = (js.get("currency") or "MAD").lower()
            rep.note("intent payload", client_secret=client_secret, amount=amount_cents, currency=currency)

            # Montant attendu = total step3 * 100
            if amount_cents is not None:
                expected_cents = int(snap3.total) * 100
                if amount_cents != expected_cents:
                    rep.error(f"Montant intent {amount_cents} ≠ attendu {expected_cents}")
                assert amount_cents == expected_cents, f"Montant intent {amount_cents} ≠ attendu {expected_cents}"

            # Tenter le “réel” si demandé
            try_real = os.environ.get("STRIPE_E2E_REAL", "0") in ("1","true","True")
            paid_via_ui = False
            if try_real:
                # 1) Elements
                try:
                    if page.locator('#payment-element, [data-test="payment-element"]').count():
                        paid_via_ui = self._try_fill_stripe_elements(page, rep)
                        if paid_via_ui:
                            try:
                                page.wait_for_selector('[data-ff-step="4"][data-thank-you]:not(.d-none)', timeout=15_000)
                            except Exception:
                                page.wait_for_url(re.compile(r".*(merci|success|thank|order).*", re.I), timeout=15_000)
                except Exception:
                    pass
                # 2) Checkout hébergé
                if not paid_via_ui:
                    paid_via_ui = self._try_fill_stripe_checkout(page, rep)
                    if paid_via_ui:
                        try:
                            page.wait_for_url(re.compile(r".*(merci|success|thank|order).*", re.I), timeout=20_000)
                        except Exception:
                            pass

            # Si pas de “réel”, simuler le webhook (source de vérité DB)
            def _pi_from_cs(cs: str) -> Optional[str]:
                if not cs: return None
                i = cs.find("_secret"); return cs[:i] if i > 0 else None

            pi_id = _pi_from_cs(client_secret)
            if not paid_via_ui:
                assert client_secret and pi_id, "client_secret/pi_id introuvable — impossible de simuler le webhook"
                ok = self._post_stripe_webhook(ctx, rep, pi_id, amount_cents or (snap3.total * 100), currency)
                assert ok, "Webhook simulé non accepté par le serveur"

            # --------- Assertions DB ----------
            order: Optional[Order] = None
            if pi_id:
                order = Order.objects.filter(stripe_payment_intent_id=pi_id).order_by("-id").first()
            if not order and amount_cents:
                order = Order.objects.filter(amount_total=amount_cents, email__iexact=email).order_by("-id").first()
            assert order is not None, "Order introuvable après paiement"
            rep.note("DB.Order", id=order.id, status=order.status, amount=order.amount_total, currency=order.currency)
            assert order.status == OrderStatus.PAID, f"Order.status={order.status} ≠ PAID"

            payment: Optional[Payment] = getattr(order, "payment", None)
            assert payment is not None, "Payment non créé"
            rep.note("DB.Payment", pi=payment.stripe_payment_intent_id, status=payment.status,
                     amount_received=payment.amount_received, currency=payment.currency)
            if amount_cents:
                assert payment.amount_received == amount_cents, "Payment.amount_received ≠ intent.amount"

            assert PaymentLog.objects.filter(order=order, event_type__icontains="succeeded").exists(), \
                "PaymentLog 'succeeded' absent"

            # merci (si UI l’affiche)
            try:
                page.wait_for_selector('[data-ff-step="4"][data-thank-you]:not(.d-none)', timeout=2000)
                rep.note("thank-you visible")
            except Exception:
                pass

            ctx.close()
            browser.close()

        # Au moins 2 progress calls (step1/step2)
        assert len( (rep.data.get("progress_calls") or []) ) >= 2, "Il manque des progress calls (step1/step2)."
        rep.finalize()
