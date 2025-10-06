from __future__ import annotations

from django.test import Client

from apps.common.runscript_harness import binary_harness


@binary_harness
def run():
    client = Client()
    response = client.get("/france/")
    ok = response.status_code == 200
    logs = [f"FR /france/ status={response.status_code}"]
    if ok and "+33 1 23 45 67 89" in response.content.decode("utf-8"):
        logs.append("Phone FR fallback detected")
    else:
        ok = False
        logs.append("Phone FR missing")
    return {"ok": ok, "name": "Smoke FR", "duration": 0.0, "logs": logs}
