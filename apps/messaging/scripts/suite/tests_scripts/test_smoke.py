from __future__ import annotations

from django.test import Client
from django.test.utils import override_settings


def run():
    client = Client()
    with override_settings(ROOT_URLCONF="lumierelearning.urls"):
        response = client.get("/email/health/")
    ok = response.status_code == 200 and response.json().get("status") == "ok"
    return {
        "ok": ok,
        "name": "test_smoke",
        "duration": 0.0,
        "logs": ["health endpoint reachable" if ok else "health endpoint missing"],
    }
