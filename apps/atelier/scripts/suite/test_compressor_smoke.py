from __future__ import annotations

from django.conf import settings
from django.test import Client


def run() -> dict[str, object]:
    client = Client()
    response = client.get("/")
    html = response.content.decode("utf-8") if response.status_code == 200 else ""
    cache_present = "CACHE/" in html
    fallback_present = "/static/css/plugins/icofont.min.css" in html
    if getattr(settings, "COMPRESS_OFFLINE", False):
        ok = response.status_code == 200 and cache_present
    else:
        ok = response.status_code == 200 and (cache_present or fallback_present)
    return {
        "ok": ok,
        "name": "compressor_smoke",
        "logs": f"status={response.status_code}, cache_present={cache_present}",
        "duration": 0.0,
    }
