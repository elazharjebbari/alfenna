from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

class ProductDetailPageTests(TestCase):
    def test_product_detail_route_returns_ok(self) -> None:
        from apps.catalog.models import Product
        from apps.catalog.models.models_catalog import Gallery, GalleryItem

        product = Product.objects.create(
            slug="pack-cosmetique-naturel",
            name="Pack",
            price=349,
            promo_price=329,
            currency="MAD",
        )
        gallery = Gallery.objects.create(slug="participants", is_active=True)
        GalleryItem.objects.create(
            gallery=gallery,
            name="Demo",
            image="images/demo.jpg",
        )

        url = reverse("pages:product-detail-slug", kwargs={"product_slug": product.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("data-cmp=\"product\"", html)
        self.assertIn("data-form-stepper", html)
        self.assertIn('data-steps="4"', html)
        self.assertIn('data-action-url="/api/leads/collect/"', html)
        self.assertIn('data-sign-url="/api/leads/sign/"', html)
        self.assertIn('data-require-signed="true"', html)
