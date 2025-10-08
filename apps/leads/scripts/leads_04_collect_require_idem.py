"""Collect endpoint must enforce X-Idempotency-Key header."""

import uuid

from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.common.runscript_harness import binary_harness
from apps.leads.constants import FormKind


@binary_harness
def run():  # pragma: no cover - executed via runscript
    client = Client()
    collect_url = reverse("leads:collect")

    body = {
        "form_kind": FormKind.CHECKOUT_INTENT,
        "full_name": "No Header",
        "phone": "+212699999999",
        "course_slug": "pack-alpha",
        "currency": "MAD",
        "accept_terms": True,
        "ff_flow_key": "checkout_intent_flow",
        "ff_session_key": f"rs-{uuid.uuid4().hex[:10]}",
        "client_ts": timezone.now().isoformat(),
    }

    resp = client.post(collect_url, data=body, content_type="application/json")
    print(f"collect status={resp.status_code}")

    return {"ok": resp.status_code == 400, "logs": [f"status={resp.status_code}"]}
