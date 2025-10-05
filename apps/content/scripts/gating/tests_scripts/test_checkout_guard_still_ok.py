"""Locked lecture page should expose checkout CTA for non-entitled users."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.content.scripts import attach_demo_media, seed_stream_demo
from apps.common.runscript_harness import binary_harness


@binary_harness
def run(*args, **kwargs):
    seed_stream_demo.run()
    attach_demo_media.run()

    User = get_user_model()
    user, _ = User.objects.get_or_create(username="browser_locked", defaults={"email": "browser_locked@example.com"})
    user.set_password("demo")
    user.save()

    client = Client()
    assert client.login(username="browser_locked", password="demo"), "Login failed"

    path = reverse("pages:lecture", kwargs={"course_slug": "stream-demo"})
    resp = client.get(path)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

    html = resp.content.decode("utf-8")
    assert 'data-locked="1"' in html, "Locked flag should remain for non-entitled user"
    from apps.atelier.compose.hydrators.learning.hydrators import _common_lecture_ctx

    ctx = _common_lecture_ctx(resp.wsgi_request, {})
    plan_slug = ctx.get("plan_slug") or ""
    expected_checkout = f"/billing/checkout/plan/{plan_slug}/" if plan_slug else "/billing/checkout/stream-demo/"
    assert f'data-checkout-url="{expected_checkout}"' in html, "Checkout CTA missing"

    return {
        "ok": True,
        "name": "test_checkout_guard_still_ok",
        "duration": 0.0,
        "logs": ["locked lecture exposes checkout url"],
    }

