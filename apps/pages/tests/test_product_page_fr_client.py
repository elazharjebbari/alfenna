from __future__ import annotations

from django.test import TestCase

from apps.marketing.models.models_pricing import PricePlan


class ProductPageFRClientTests(TestCase):
    fixtures = ["alfenna/fixtures/product_pack_cosmetique_naturel.json"]

    @classmethod
    def setUpTestData(cls) -> None:
        plan, _ = PricePlan.objects.get_or_create(
            slug="createur",
            defaults=dict(
                title="Createur",
                currency="MAD",
                currency_symbol="MAD",
                price_cents=32900,
                is_active=True,
            ),
        )
        plan.title = "TITRE_DB_SENTINEL"
        plan.features = ["FEATURE_DB_SENTINEL"]
        plan.save()

    def test_product_page_fr_displays_db_sentinels(self) -> None:
        candidates = (
            "/produits/pack-cosmetique-naturel/",
            "/maroc/produits/pack-cosmetique-naturel/",
            "/maroc/fr/produits/pack-cosmetique-naturel/",
        )
        response = None
        matched_url = None
        for url in candidates:
            response = self.client.get(url, follow=True)
            if response.status_code == 200:
                matched_url = url
                break

        self.assertIsNotNone(matched_url, f"Aucune URL candidate n'a renvoyé 200: {candidates}")
        content = response.content.decode("utf-8")
        self.assertIn("Pack cosmétique naturel", content)
        self.assertIn("100% naturel", content)
        self.assertIn("/static/images/landing-page/product-single/pack-detail-1.webp", content)
        self.assertIn("TITRE_DB_SENTINEL", content)
        self.assertIn("FEATURE_DB_SENTINEL", content)
