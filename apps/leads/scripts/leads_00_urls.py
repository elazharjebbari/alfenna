"""Sanity checks for leads API endpoints."""

from django.test import Client
from django.urls import reverse

from apps.common.runscript_harness import binary_harness


@binary_harness
def run():  # pragma: no cover - executed via runscript
    client = Client()
    urls = {
        "sign": reverse("leads:sign"),
        "collect": reverse("leads:collect"),
        "progress": reverse("leads:progress"),
    }

    logs: list[str] = []

    for name, url in urls.items():
        logs.append(f"→ {name} => {url}")

    # Smoke POSTs
    sign_resp = client.post(urls["sign"], data={}, content_type="application/json")
    logs.append(f"sign status={sign_resp.status_code}")
    collect_resp = client.post(urls["collect"], data={}, content_type="application/json")
    logs.append(f"collect status={collect_resp.status_code}")
    progress_resp = client.post(urls["progress"], data={}, content_type="application/json")
    logs.append(f"progress status={progress_resp.status_code}")

    ok = sign_resp.status_code in {200, 400} and collect_resp.status_code in {400, 405} and progress_resp.status_code == 400

    for line in logs:
        print(line)

    return {"ok": ok, "logs": logs}
