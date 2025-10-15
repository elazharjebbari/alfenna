from __future__ import annotations

from django.test import TestCase

from apps.marketing.models.models_pricing import PricePlan


class ProductPageDbFirstFixturesTests(TestCase):
    fixtures = [
        "products_pack_cosmetique.json",
        "catalog_images.json",
        "alfenna/fixtures/price_plans.json",
    ]

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
        plan.currency = "MAD"
        plan.currency_symbol = "MAD"
        plan.is_active = True
        plan.save(update_fields=["currency", "currency_symbol", "is_active"])

    def test_product_hero_displays_product_from_db(self) -> None:
        response = self.client.get("/produits/pack-cosmetique-naturel/", follow=True)
        self.assertEqual(response.status_code, 200, response.content[:200])

        html = response.content.decode("utf-8")
        self.assertIn("Le rituel spa antifongique 100% naturel — Pack <strong>8&nbsp;pièces</strong>", html)
        self.assertIn("sérum, gel, hydratant, trousse, pierre ponce, lime, coupe-ongles, serviette.", html)
        self.assertIn("Pack complet pour <strong>pieds &amp; ongles</strong>", html)
        self.assertIn("Restaure la beauté naturelle des ongles", html)
        self.assertIn("Sans parabènes", html)
        self.assertIn("Formule douce", html)
        self.assertIn("347 MAD", html)
        self.assertIn("450 MAD", html)
        self.assertIn("/static/images/landing-page/product-single/sac-3.png", html)
        self.assertIn("/static/images/landing-page/product-single/sac-2.png", html)

    def test_gallery_section_uses_catalog_images_fixture(self) -> None:
        response = self.client.get("/produits/pack-cosmetique-naturel/", follow=True)
        self.assertEqual(response.status_code, 200, response.content[:200])

        html = response.content.decode("utf-8")
        self.assertIn("Avis WhatsApp — clients ravis", html)
        self.assertIn("Captures réelles publiées avec consentement.", html)
        self.assertIn("Témoignages vérifiés WhatsApp", html)
        self.assertIn("Note moyenne 4,8/5", html)
        self.assertIn("500+ clients satisfaits", html)
        self.assertIn("/static/images/landing-page/testimonials/img-1.png", html)
        self.assertIn("/static/images/landing-page/testimonials/img-6.png", html)
        self.assertIn("Offert à mon épouse", html)

    def test_cross_sell_from_fixture_is_exposed(self) -> None:
        response = self.client.get("/produits/pack-cosmetique-naturel/", follow=True)
        self.assertEqual(response.status_code, 200, response.content[:200])

        html = response.content.decode("utf-8")
        self.assertIn("+ Bougie de massage hydratante", html)
        self.assertIn("40.00", html)
        self.assertIn("MAD", html)
