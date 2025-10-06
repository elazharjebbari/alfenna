from __future__ import annotations

from django.test import Client

from apps.common.runscript_harness import binary_harness


@binary_harness
def run():
    client = Client()
    response = client.get("/maroc/")
    ok = response.status_code == 200
    logs = [f"MA /maroc/ status={response.status_code}"]
    if ok and "+212 600 000 000" in response.content.decode("utf-8"):
        logs.append("Phone MA detected")
    else:
        ok = False
        logs.append("Phone MA missing")
    return {"ok": ok, "name": "Smoke MA", "duration": 0.0, "logs": logs}
