"""Outil CLI pour vérifier le flux consentement en production."""

from __future__ import annotations

import sys
from typing import Iterable

import requests

URLS: Iterable[str] = (
    "https://lumiereacademy.com/",
)


def run() -> None:
    ok = True
    for url in URLS:
        try:
            resp = requests.get(url, timeout=10)
        except requests.RequestException as exc:  # pragma: no cover - réseau prod
            print(url, "REQUEST FAILED", exc)
            ok = False
            continue

        print(url, resp.status_code)
        name = resp.headers.get("X-Consent-Marketing-Name")
        value = resp.headers.get("X-Consent-Marketing-Value")
        print("  X-Consent:", name, value)
        has_bootstrap = "/static/site/analytics_bootstrap.js" in resp.text
        print("  has bootstrap:", has_bootstrap)
        if not has_bootstrap:
            ok = False
    if not ok:
        print("SMOKE FAIL")
        sys.exit(2)
    print("SMOKE OK")


def runscript() -> None:
    run()


if __name__ == "__main__":
    run()
