"""Probe to ensure checkout assets expose Payment Request Button instrumentation."""
from __future__ import annotations

import re

from django.test import Client

from apps.common.runscript_harness import binary_harness
from apps.marketing.models.models_pricing import PricePlan


def ensure_plan() -> PricePlan:
    plan = PricePlan.objects.filter(is_active=True).order_by("display_order", "id").first()
    if plan:
        return plan
    return PricePlan.objects.create(
        slug="test-plan",
        title="Test Plan",
        price_cents=9900,
        is_active=True,
    )


@binary_harness
def run(*_args, **_kwargs):
    plan = ensure_plan()
    client = Client()

    path = f"/billing/checkout/plan/{plan.slug}/"
    resp = client.get(path)

    logs: list[str] = [f"GET {path} => {resp.status_code}"]
    if resp.status_code != 200:
        logs.append("Unexpected status code for checkout page")
        return {"ok": False, "name": "checkout_assets_probe", "duration": 0.0, "logs": logs}

    html = resp.content.decode("utf-8", "ignore")
    prb_present = 'id="payment-request-button"' in html
    logs.append(f"payment-request-button present: {'OK' if prb_present else 'KO'}")

    thankyou_bootstrap = 'thankYouUrl' in html
    logs.append(f"thankYouUrl bootstrap: {'OK' if thankyou_bootstrap else 'KO'}")

    match = re.search(r'src="(?P<url>[^"]*checkout\.js[^"]*)"', html)
    if not match:
        logs.append("checkout.js bundle URL not found in HTML")
        return {"ok": False, "name": "checkout_assets_probe", "duration": 0.0, "logs": logs}

    bundle_url = match.group('url')
    if bundle_url.startswith("http://") or bundle_url.startswith("https://"):
        asset_path = bundle_url
    elif bundle_url.startswith("//"):
        asset_path = f"https:{bundle_url}"
    elif bundle_url.startswith('/'):
        asset_path = bundle_url
    else:
        asset_path = '/' + bundle_url.lstrip('/')

    asset_resp = client.get(asset_path)
    logs.append(f"GET {asset_path} => {asset_resp.status_code}")
    if asset_resp.status_code != 200:
        logs.append("Unable to fetch checkout.js bundle from server")
        return {"ok": False, "name": "checkout_assets_probe", "duration": 0.0, "logs": logs}

    if getattr(asset_resp, "streaming", False):
        bundle_bytes = b"".join(asset_resp.streaming_content)
    else:
        bundle_bytes = asset_resp.content

    bundle_text = bundle_bytes.decode("utf-8", "ignore")
    guard_line = "Veuillez vérifier que vos adresses e-mail sont correctes et identiques."
    has_guard = guard_line in bundle_text
    logs.append(f"guard line present: {'OK' if has_guard else 'KO'}")

    handler_present = "paymentRequest.on('paymentmethod'" in bundle_text or 'paymentRequest.on("paymentmethod"' in bundle_text
    logs.append(f"paymentmethod handler wired: {'OK' if handler_present else 'KO'}")

    build_thankyou_present = 'buildThankYouUrl' in bundle_text
    logs.append(f"buildThankYouUrl present: {'OK' if build_thankyou_present else 'KO'}")

    return_url_present = 'return_url' in bundle_text
    logs.append(f"return_url usage present: {'OK' if return_url_present else 'KO'}")

    logs.append("DevTools hint: disable cache, hard reload checkout, open checkout.js and search for the guard line.")

    ok = prb_present and has_guard and handler_present and thankyou_bootstrap and build_thankyou_present and return_url_present
    return {"ok": ok, "name": "checkout_assets_probe", "duration": 0.0, "logs": logs}
