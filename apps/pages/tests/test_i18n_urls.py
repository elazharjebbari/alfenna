from __future__ import annotations

from typing import Dict

from django.test import TestCase
from django.utils import translation
from django.utils.translation import gettext as _


class PageI18nRoutingTests(TestCase):
    def test_localized_homepages_are_served(self) -> None:
        expectations: Dict[str, str] = {
            "fr": "NATUREL • SOIN • CONFIANCE",
            "en": "NATURAL • CARE • TRUST",
            "ar": "طبيعي • عناية • ثقة",
        }

        for lang, expected in expectations.items():
            response = self.client.get(f"/{lang}/")
            self.assertEqual(response.status_code, 200, msg=f"/{lang}/ should resolve")
            self.assertEqual(response.headers.get("Content-Language"), lang)

            with translation.override(lang):
                self.assertEqual(_("NATUREL • SOIN • CONFIANCE"), expected)

        sitemap_response = self.client.get("/sitemap.xml")
        self.assertEqual(sitemap_response.status_code, 200)
