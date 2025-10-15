from __future__ import annotations

from django.test import TestCase

from apps.atelier.i18n.translation_service import TranslationService
from apps.catalog.models import Product
from apps.i18n.models import StringTranslation
from apps.i18n.utils import build_translation_key, parse_translation_key


class DBTranslationProviderTests(TestCase):
    fixtures = []

    def setUp(self) -> None:
        self.product = Product.objects.create(
            slug="test-product",
            name="Nom FR",
            subname="Sous-titre FR",
            description="Description FR",
            price=199,
            currency="MAD",
        )

    def test_falls_back_to_default_when_missing(self) -> None:
        key_core = build_translation_key(self.product, "name")
        service = TranslationService(locale="ar", site_version="ma")

        translated = service.t(key_core, default=self.product.name)

        self.assertEqual(translated, self.product.name)

    def test_returns_french_translation_before_default(self) -> None:
        key_core = build_translation_key(self.product, "name")
        model_label, object_id, field_path = parse_translation_key(key_core)
        StringTranslation.objects.create(
            model_label=model_label,
            object_id=object_id,
            field=field_path,
            language="fr",
            text="Nom FR DB",
            status="active",
            source="manual",
        )

        service = TranslationService(locale="ar", site_version="ma")

        translated = service.t(key_core, default=self.product.name)

        self.assertEqual(translated, "Nom FR DB")

    def test_returns_locale_specific_translation(self) -> None:
        key_core = build_translation_key(self.product, "name")
        label, object_id, field_path = parse_translation_key(key_core)
        StringTranslation.objects.create(
            model_label=label,
            object_id=object_id,
            field=field_path,
            language="fr",
            text="Nom FR DB",
            status="active",
            source="manual",
        )

        key_ar = build_translation_key(self.product, "name", site_version="ma")
        _, _, field_path_ar = parse_translation_key(key_ar)
        StringTranslation.objects.create(
            model_label=label,
            object_id=object_id,
            field=field_path_ar,
            language="ar",
            text="اسم عربي",
            status="active",
            source="manual",
        )

        service = TranslationService(locale="ar", site_version="ma")

        translated = service.t(key_core, default=self.product.name)

        self.assertEqual(translated, "اسم عربي")
