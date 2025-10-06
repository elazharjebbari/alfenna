"""Smoke check ensuring checkout plan bootstrap exposes thank-you URL."""
from __future__ import annotations

import re

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


def extract_bootstrap_value(html: str, key: str) -> str | None:
    pattern = rf"{key}\s*:\s*\"([^\"]*)\""
    match = re.search(pattern, html)
    return match.group(1) if match else None


@binary_harness
def run(*_args, **_kwargs):
    plan = ensure_plan()
    client = Client()

    path = reverse("pages:checkout", kwargs={"plan_slug": plan.slug})
    resp = client.get(path)

    logs: list[str] = [f"GET {path} => {resp.status_code}"]
    if resp.status_code != 200:
        logs.append("Unexpected status code for checkout page")
        return {"ok": False, "name": "checkout_plan_smoke", "duration": 0.0, "logs": logs}

    html = resp.content.decode("utf-8", "ignore")
    plan_slug_boot = extract_bootstrap_value(html, "planSlug")
    thank_url_boot = extract_bootstrap_value(html, "thankYouUrl")

    expected_thank_you = reverse("pages:thank-you", kwargs={"plan_slug": plan.slug})

    checks = [
        (plan.title in html, "plan title present"),
        ("window.__CHECKOUT__" in html, "bootstrap present"),
        (plan_slug_boot == plan.slug, "planSlug matches"),
        (thank_url_boot == expected_thank_you, "thankYouUrl matches"),
    ]

    for ok, label in checks:
        logs.append(f"{label}: {'OK' if ok else 'KO'}")
        if not ok:
            return {"ok": False, "name": "checkout_plan_smoke", "duration": 0.0, "logs": logs}

    logs.append("Bootstrap exposes correct thank-you URL.")
    return {"ok": True, "name": "checkout_plan_smoke", "duration": 0.0, "logs": logs}
