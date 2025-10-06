from __future__ import annotations

import time

from django.test import Client

from apps.common.runscript_harness import binary_harness

PAGES = [
    ("/", "/maroc/"),
    ("/test", "/maroc/test"),
    ("/contact", "/maroc/contact"),
    ("/courses", "/maroc/courses"),
    ("/", "/france/"),
    ("/test", "/france/test"),
    ("/contact", "/france/contact"),
    ("/courses", "/france/courses"),
]


@binary_harness
def run():
    start = time.time()
    client = Client()
    ok = True
    logs: list[str] = []

    for core_url, ma_url in PAGES:
        rc = client.get(core_url).status_code
        rm = client.get(ma_url).status_code
        logs.append(f"[core:{rc}] {core_url} — [ma:{rm}] {ma_url}")
        if rc != 200 or rm != 200:
            ok = False

    return {
        "ok": ok,
        "name": "Crawl core/ma",
        "duration": round(time.time() - start, 2),
        "logs": logs,
    }
