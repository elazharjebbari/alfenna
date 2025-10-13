from __future__ import annotations

from typing import List, Tuple

from django.test import Client

from apps.common.runscript_harness import binary_harness


@binary_harness
def run():
    client = Client()
    checks: List[Tuple[str, str, bool]] = [
        ("/", "core", False),
        ("/maroc/", "ma", False),
    ]

    ok = True
    logs: List[str] = []
    for path, expected_ns, force_ar in checks:
        headers = {"HTTP_ACCEPT_LANGUAGE": "ar"} if force_ar else {}
        response = client.get(path, follow=False, **headers)
        site_version = getattr(response.wsgi_request, "site_version", None)
        lang = getattr(getattr(response.wsgi_request, "_segments", None), "lang", None)
        passed = response.status_code in (200, 301, 302) and site_version == expected_ns
        ok = ok and passed
        status_label = "OK" if passed else "FAIL"
        message = (
            f"[smoke_versions] {status_label} path={path} status={response.status_code} "
            f"site_version={site_version} lang={lang}"
        )
        print(message)
        logs.append(message)

    return {"ok": ok, "name": "smoke_versions", "duration": 0.0, "logs": logs}
