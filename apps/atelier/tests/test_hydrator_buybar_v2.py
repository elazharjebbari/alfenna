from django.test import TestCase, RequestFactory
from django.urls import reverse, resolve

from apps.catalog.models import Product
from apps.atelier.compose.hydrators.sticky.hydrators import buybar_v2


class BuybarV2HydratorTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_db_first_payload(self) -> None:
        product = Product.objects.create(
            slug="pack-cosmetique-naturel",
            name="Pack 8 pièces",
            price=349,
            promo_price=347,
            currency="MAD",
        )
        url = reverse("pages:product-detail-slug", kwargs={"product_slug": product.slug})
        request = self.factory.get(url)
        request.resolver_match = resolve(url)

        ctx = buybar_v2(request, {
            "title_fallback": "fallback",
            "discount_label": "Sac +\n4 articles offerts",
            "cta_label": "Je commande le pack",
        })

        self.assertEqual(ctx["product_slug"], product.slug)
        self.assertTrue(ctx["product_found"])
        self.assertEqual(ctx["amount"], 347.0)
        self.assertEqual(ctx["currency"], "MAD")
        self.assertEqual(ctx["title"], "Pack 8 pièces")
        self.assertEqual(ctx["cta_label"], "Je commande le pack")
        self.assertEqual(ctx["discount_label"], "Sac +\n4 articles offerts")

    def test_fallback_when_product_missing(self) -> None:
        url = reverse("pages:product-detail-slug", kwargs={"product_slug": "inconnu"})
        request = self.factory.get(url)
        request.resolver_match = resolve(url)
        ctx = buybar_v2(request, {"title_fallback": "fallback title"})

        self.assertFalse(ctx["product_found"])
        self.assertEqual(ctx["title"], "fallback title")
        self.assertIsNone(ctx["amount"])
