from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Product


class ProductDetailFabWhatsappTests(TestCase):
    def setUp(self) -> None:
        self.product = Product.objects.create(
            slug="pack-cosmetique-naturel",
            name="Pack Cosmétiques",
            price=349,
            promo_price=329,
            currency="MAD",
        )

    def test_fab_whatsapp_is_rendered_with_expected_attributes(self) -> None:
        url = reverse("pages:product-detail-slug", kwargs={"product_slug": self.product.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        html = response.content.decode()
        self.assertIn('data-cmp="fab-whatsapp"', html)
        self.assertIn('aria-label="Contacter sur WhatsApp"', html)
        self.assertIn('href="https://wa.me/212719646705', html)
        self.assertIn('target="_blank"', html)
        self.assertIn('rel="noopener"', html)
        self.assertIn('right: 16px', html)
        self.assertIn('bottom: 18px', html)
        self.assertIn('Besoin d’aide ?', html)
