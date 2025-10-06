"""Quick smoke checks for ``X-Robots-Tag`` headers on key routes."""

from __future__ import annotations

from django.test import Client
from django.test.utils import override_settings

PUBLIC_URLS = (
    "/",
    "/contact",
    "/packs",
)

PRIVATE_URLS = (
    "/admin/login/",
)


def _normalize(header: str | None) -> str:
    if not header:
        return ""
    return header.replace(" ", "").lower()


def run(*args) -> None:  # pragma: no cover - manual smoke helper
    with override_settings(SEO_ENV="prod"):
        client = Client()

        for url in PUBLIC_URLS:
            response = client.get(url, follow=True)
            header = _normalize(response.get("X-Robots-Tag"))
            status = response.status_code
            outcome = "OK" if status == 200 and header == "index,follow" else "FAIL"
            print(f"public {url} status={status} x-robots={header} -> {outcome}")

        for url in PRIVATE_URLS:
            response = client.get(url, follow=True)
            header = _normalize(response.get("X-Robots-Tag"))
            status = response.status_code
            outcome = "OK" if header == "noindex,nofollow" else "FAIL"
            print(f"private {url} status={status} x-robots={header} -> {outcome}")
