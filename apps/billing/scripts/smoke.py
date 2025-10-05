"""Basic smoke tests for public billing endpoints."""
from __future__ import annotations

from django.conf import settings
from django.test import Client
from django.urls import reverse

from apps.common.runscript_harness import binary_harness, skip


@binary_harness
def run(*_args, **_kwargs):
    if not getattr(settings, "BILLING_ENABLED", False):
        return skip("BILLING_ENABLED toggle is disabled")

    client = Client()
    targets = [
        ("billing:success", "billing-outcome--success"),
        ("billing:cancel", "billing-outcome--cancel"),
        ("billing:health", None),
    ]

    logs: list[str] = []
    for name, marker in targets:
        url = reverse(name)
        resp = client.get(url)
        logs.append(f"GET {url} -> {resp.status_code}")
        if resp.status_code != 200:
            return {"ok": False, "name": "billing_smoke", "duration": 0.0, "logs": logs}
        if marker and marker not in resp.content.decode("utf-8", "ignore"):
            logs.append(f"marker {marker} missing in response body")
            return {"ok": False, "name": "billing_smoke", "duration": 0.0, "logs": logs}
    logs.append("billing endpoints reachable")
    return {"ok": True, "name": "billing_smoke", "duration": 0.0, "logs": logs}
