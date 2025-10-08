from django.test import TestCase
from django.urls import reverse


class ProductDetailStickyBuybarTests(TestCase):
    def setUp(self) -> None:
        from apps.catalog.models import Product
        from apps.catalog.models.models_catalog import Gallery, GalleryItem

        self.product = Product.objects.create(
            slug="pack-cosmetique-naturel",
            name="Pack",
            price=349,
            promo_price=347,
            currency="MAD",
        )
        gallery = Gallery.objects.create(slug="participants", is_active=True)
        GalleryItem.objects.create(
            gallery=gallery,
            name="Demo",
            image="images/demo.jpg",
            webp="",
            href="",
        )

    def test_sticky_buybar_rendered(self) -> None:
        url = reverse("pages:product-detail-slug", kwargs={"product_slug": self.product.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"af-buybar-v2", response.content)
