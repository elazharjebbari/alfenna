"""Crawl the main billing routes and report their status codes."""
from __future__ import annotations

import time

from django.conf import settings
from django.test import Client
from django.urls import reverse

from apps.common.runscript_harness import binary_harness, skip


TARGETS = [
    ("GET", "billing:success", {}),
    ("GET", "billing:cancel", {}),
    ("GET", "billing:health", {}),
]


@binary_harness
def run(*_args, **_kwargs):
    if not getattr(settings, "BILLING_ENABLED", False):
        return skip("BILLING_ENABLED toggle is disabled")

    client = Client()
    logs: list[str] = []
    failures: list[str] = []
    for method, name, kwargs in TARGETS:
        url = reverse(name, kwargs=kwargs)
        start = time.perf_counter()
        response = client.generic(method, url)
        duration_ms = (time.perf_counter() - start) * 1000
        logs.append(f"{method} {url} -> {response.status_code} ({duration_ms:.1f}ms)")
        if response.status_code >= 400:
            failures.append(f"{method} {url}")
    if failures:
        logs.append(f"Failures: {', '.join(failures)}")
        return {"ok": False, "name": "billing_crawler", "duration": 0.0, "logs": logs}
    logs.append("All billing endpoints responded successfully")
    return {"ok": True, "name": "billing_crawler", "duration": 0.0, "logs": logs}
