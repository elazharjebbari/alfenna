from __future__ import annotations

from django.test import SimpleTestCase

from apps.atelier.i18n.providers import YamlCatalogProvider
from apps.atelier.i18n.translation_service import TranslationService


class TranslationServiceTests(SimpleTestCase):
    def setUp(self) -> None:
        self.service = TranslationService(locale="ar", site_version="ma")

    def test_walk_translates_t_prefix(self) -> None:
        result = self.service.walk("t:header.menu.home")

        self.assertEqual(result, "الرئيسية")

    def test_walk_translates_dict_token(self) -> None:
        payload = {"label": {"t": "header.menu.contact"}, "count": 2}

        result = self.service.walk(payload)

        self.assertEqual(result["label"], "تواصل معنا")
        self.assertEqual(result["count"], 2)

    def test_walk_handles_nested_sequences(self) -> None:
        payload = [
            "t:header.menu.home",
            {"t": "header.menu.faq"},
            ("t:header.menu.product", "raw"),
        ]

        result = self.service.walk(payload)

        self.assertEqual(result[0], "الرئيسية")
        self.assertEqual(result[1], "الأسئلة الشائعة")
        self.assertEqual(result[2][0], "حزمة ألفينا")
        self.assertEqual(result[2][1], "raw")

    def test_t_returns_default_when_missing(self) -> None:
        self.assertEqual(
            self.service.t("not.a.real.key", default="fallback"),
            "fallback",
        )

    def test_walk_keeps_unknown_values(self) -> None:
        payload = {"title": "Plain text", "amount": 42}

        result = self.service.walk(payload)

        self.assertEqual(result["title"], "Plain text")
        self.assertEqual(result["amount"], 42)

    def test_missing_key_falls_back_to_source_and_is_tracked(self) -> None:
        value = "t:missing.key"

        translated = self.service.walk(value)

        self.assertEqual(translated, value)
        self.assertIn("missing.key", self.service.missing_keys)

    def test_excluded_keys_are_not_translated(self) -> None:
        payload = {
            "url": "/static/images/logo.webp",
            "label": "t:header.menu.home",
            "items": [
                {"icon": "fas fa-home", "url": "/home"},
            ],
        }

        result = self.service.walk(payload)

        self.assertEqual(result["url"], "/static/images/logo.webp")
        self.assertEqual(result["label"], "الرئيسية")
        self.assertEqual(result["items"][0]["icon"], "fas fa-home")
        self.assertEqual(result["items"][0]["url"], "/home")

    def test_no_i18n_flag_skips_translation(self) -> None:
        payload = {"_no_i18n": True, "label": "t:header.menu.home"}

        result = self.service.walk(payload)

        self.assertNotIn("_no_i18n", result)
        self.assertEqual(result["label"], "t:header.menu.home")

    def test_resolved_keys_tracks_success(self) -> None:
        self.service.t("header.menu.home")

        self.assertIn("header.menu.home", self.service.resolved_keys)

    def test_empty_provider_value_falls_back(self) -> None:
        class DummyProvider:
            def get(self, key: str, *, locale: str, site_version: str) -> str:
                return ""

        custom_service = TranslationService(
            locale="fr",
            site_version="core",
            providers=[DummyProvider(), YamlCatalogProvider()],
        )

        translated = custom_service.t("header.menu.home", default="Accueil FR")

        self.assertEqual(translated, "Accueil")
