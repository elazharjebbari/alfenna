from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

import re

from apps.atelier.config.loader import clear_config_cache
from apps.atelier.compose.hydrators.learning.hydrators import _common_lecture_ctx
from apps.billing.models import Entitlement
from apps.common.runscript_harness import binary_harness
from apps.content.scripts import seed_stream_demo


@binary_harness
def run(*args, **kwargs):
    logs = []
    clear_config_cache()
    seed_stream_demo.run()

    user, _ = User.objects.get_or_create(username="viewer_lock", defaults={"email": "viewer@example.com"})
    user.set_password("testpass")
    user.save()
    Entitlement.objects.filter(user=user).delete()

    client = Client()
    assert client.login(username="viewer_lock", password="testpass"), "Login should succeed"
    session = client.session
    session["entitled_course_ids"] = []
    session.save()

    url = reverse("pages:lecture", kwargs={"course_slug": "stream-demo"})
    response = client.get(url)

    assert response.status_code == 200, f"Authenticated viewer should reach page, got {response.status_code}"
    html = response.content.decode("utf-8")
    match = re.search(r'data-locked="([^"]+)"', html)
    value = match.group(1) if match else None
    ctx = _common_lecture_ctx(response.wsgi_request, {})
    hydrator_locked = ctx.get("is_locked")
    logs.append(f"hydrator_locked={hydrator_locked} subscribed={ctx.get('is_subscribed')}")
    logs.append(f"locked_attr={value}")
    assert hydrator_locked is True, "Hydrator should mark lecture as locked"
    plan_slug = ctx.get("plan_slug") or ""
    expected_checkout = f"/billing/checkout/plan/{plan_slug}/" if plan_slug else "/billing/checkout/stream-demo/"
    assert f'data-checkout-url="{expected_checkout}"' in html, "Checkout URL missing"

    return {"ok": True, "name": "lecture_guard_entitlement", "duration": 0.0, "logs": logs}
