from __future__ import annotations

from django.test import SimpleTestCase

from apps.atelier.i18n import service as i18n_service


class AtelierI18NTests(SimpleTestCase):
    def test_load_catalog_uses_site_version_override(self) -> None:
        catalog = i18n_service.load_catalog("ar", "ma")

        self.assertIn("footer", catalog)
        self.assertEqual(catalog["footer"]["shop"], "المتجر")

    def test_t_key_lookup_and_default(self) -> None:
        translated = i18n_service.t("footer.shop", "fr", "core")
        self.assertEqual(translated, "Boutique")

        untouched = i18n_service.t("Plain text sentence", "fr", "core")
        self.assertEqual(untouched, "Plain text sentence")

    def test_i18n_walk_nested_translates_keys(self) -> None:
        payload = {
            "title": "faq.title_html",
            "items": ["footer.shop", {"label": "footer.support"}, 42],
            "metadata": ("footer.brand", "unchanged"),
        }

        converted = i18n_service.i18n_walk(payload, "ar", "ma")

        self.assertIn("الأسئلة", converted["title"])
        self.assertEqual(converted["items"][0], "المتجر")
        self.assertEqual(converted["items"][1]["label"], "الدعم")
        self.assertEqual(converted["items"][2], 42)
        self.assertEqual(converted["metadata"][0], "ألفينا")
        self.assertEqual(converted["metadata"][1], "unchanged")
