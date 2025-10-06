"""Probe createIntent endpoint and thank-you redirection readiness."""
from __future__ import annotations

import json

from django.test import Client
from django.urls import reverse

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

    create_url = reverse("billing:create_payment_intent")
    payload = {
        "plan_slug": plan.slug,
        "email": "wallet@example.com",
        "currency": "EUR",
    }

    resp = client.post(create_url, data=json.dumps(payload), content_type="application/json")
    logs: list[str] = [f"POST {create_url} => {resp.status_code}"]
    if resp.status_code != 200:
        logs.append(resp.content.decode("utf-8", "ignore"))
        return {"ok": False, "name": "checkout_intent_probe", "duration": 0.0, "logs": logs}

    data = resp.json()
    client_secret = data.get("clientSecret")
    order_id = data.get("orderId")

    checks = [
        (bool(client_secret), "clientSecret present"),
        (bool(order_id), "orderId present"),
    ]
    for ok, label in checks:
        logs.append(f"{label}: {'OK' if ok else 'KO'}")
        if not ok:
            return {"ok": False, "name": "checkout_intent_probe", "duration": 0.0, "logs": logs}

    thank_you_base = reverse("pages:thank-you", kwargs={"plan_slug": plan.slug})
    thank_you_url = f"{thank_you_base}?order={order_id}" if order_id else thank_you_base

    head_resp = client.get(thank_you_url)
    logs.append(f"GET {thank_you_url} => {head_resp.status_code}")
    if head_resp.status_code != 200:
        logs.append("Thank-you page not reachable with order parameter")
        return {"ok": False, "name": "checkout_intent_probe", "duration": 0.0, "logs": logs}

    logs.append("PaymentIntent endpoint operational for plan checkout.")
    return {"ok": True, "name": "checkout_intent_probe", "duration": 0.0, "logs": logs}
