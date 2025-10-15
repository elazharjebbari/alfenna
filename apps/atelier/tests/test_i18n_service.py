from __future__ import annotations

from django.test import RequestFactory, SimpleTestCase

from apps.atelier.i18n.service import direction, resolve_locale, translate


class I18NServiceTests(SimpleTestCase):
    factory = RequestFactory()

    def test_resolve_locale_from_site_version_ma_returns_ar(self) -> None:
        request = self.factory.get("/")
        request.site_version = "ma"

        locale = resolve_locale(request)

        self.assertEqual(locale, "ar")

    def test_resolve_locale_query_param_has_priority(self) -> None:
        request = self.factory.get("/?lang=fr")
        request.site_version = "ma"

        locale = resolve_locale(request)

        self.assertEqual(locale, "fr")

    def test_direction_ar_is_rtl_fr_is_ltr(self) -> None:
        self.assertEqual(direction("ar"), "rtl")
        self.assertEqual(direction("fr"), "ltr")

    def test_t_prefix_resolves_catalog_key(self) -> None:
        translated = translate("t:footer.shop", "ar", "ma")

        self.assertEqual(translated, "المتجر")

    def test__i18n_map_selects_correct_variant(self) -> None:
        payload = {"_i18n": {"fr": "Bonjour", "ar": "مرحبا"}}

        translated = translate(payload, "ar", "ma")

        self.assertEqual(translated, "مرحبا")

    def test_no_i18n_subtree_is_preserved(self) -> None:
        payload = {"_no_i18n": True, "value": "Keep"}

        translated = translate(payload, "ar", "ma")

        self.assertEqual(translated, payload)
        self.assertIsNot(translated, payload)
