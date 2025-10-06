"""Smoke test for plan-based checkout route."""
from __future__ import annotations

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
def run(*args, **kwargs):
    plan = ensure_plan()
    client = Client()

    path = f"/billing/checkout/plan/{plan.slug}/"
    resp = client.get(path)

    if resp.status_code != 200:
        return {
            "ok": False,
            "name": "test_checkout_plan_route",
            "duration": 0.0,
            "logs": [f"GET {path} => {resp.status_code}"],
        }

    html = resp.content.decode("utf-8", "ignore")
    checks = [
        (plan.title in html, "plan title present"),
        ("window.__CHECKOUT__" in html, "bootstrap script present"),
        (f"planSlug: \"{plan.slug}\"" in html or f'planSlug: \"{plan.slug}\"' in html, "plan slug encoded"),
        ("thankYouUrl" in html, "thankYouUrl present"),
    ]
    logs = [f"GET {path} => {resp.status_code}"]
    for ok, label in checks:
        logs.append(f"{label}: {'OK' if ok else 'KO'}")
        if not ok:
            return {"ok": False, "name": "test_checkout_plan_route", "duration": 0.0, "logs": logs}

    return {"ok": True, "name": "test_checkout_plan_route", "duration": 0.0, "logs": logs}
