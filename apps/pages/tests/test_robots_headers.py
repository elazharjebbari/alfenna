from __future__ import annotations

from django.test import TestCase, override_settings
from django.urls import reverse


def _normalize(header: str | None) -> str:
    if header is None:
        return ""
    return header.replace(" ", "").lower()


@override_settings(SEO_ENV="prod")
class RobotsHeaderTests(TestCase):
    def test_public_pages_expose_index_follow_header(self) -> None:
        public_urls = [
            "/",
            reverse("pages:contact"),
            reverse("pages:packs"),
        ]

        for url in public_urls:
            response = self.client.get(url, follow=True)
            self.assertEqual(response.status_code, 200, msg=f"Unexpected status for {url}")
            self.assertEqual(_normalize(response.get("X-Robots-Tag")), "index,follow")

    def test_admin_login_remains_noindex(self) -> None:
        response = self.client.get("/admin/login/", follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(_normalize(response.get("X-Robots-Tag")), "noindex,nofollow")
