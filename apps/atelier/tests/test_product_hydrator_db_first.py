from __future__ import annotations

from types import SimpleNamespace

from django.test import RequestFactory, TestCase

from apps.atelier.compose.hydrators.product.product import hydrate_product
from apps.catalog.models import Product


class ProductHydratorDbFirstTests(TestCase):
    fixtures = ["products_pack_cosmetique.json"]

    def setUp(self) -> None:
        self.factory = RequestFactory()

    def _request(self, slug: str) -> object:
        request = self.factory.get(f"/produits/{slug}/")
        request._product_slug = slug
        request.resolver_match = SimpleNamespace(kwargs={"product_slug": slug})
        return request

    def test_hydrates_from_database_when_product_exists(self) -> None:
        slug = "pack-cosmetique-naturel"
        product = Product.objects.get(slug=slug)
        request = self._request(slug)

        context = hydrate_product(
            request,
            params={
                "lookup": {"slug": "{{ url.kwargs.product_slug }}"},
                "form": {"alias": "core/forms/lead_step3"},
            },
        )

        self.assertEqual(context["product"]["id"], str(product.id))
        self.assertEqual(context["product"]["name"], product.name)
        self.assertEqual(context["product"]["slug"], product.slug)
        self.assertTrue(context["pricing"]["has_promo"])
        self.assertTrue(any(img.get("src") for img in context["media"]["images"]))
        cross_sells = context.get("cross_sells", [])
        self.assertTrue(any(item.get("slug") == "bougie-massage-hydratante" for item in cross_sells))

    def test_fallback_to_config_when_product_missing(self) -> None:
        slug = "inconnu"
        request = self._request(slug)

        context = hydrate_product(
            request,
            params={
                "lookup": {"slug": slug},
                "product": {"name": "Produit Config", "slug": slug, "price": 199, "currency": "MAD"},
                "form": {"alias": "core/forms/lead_step3"},
            },
        )

        self.assertEqual(context["product"]["name"], "Produit Config")
        self.assertEqual(context["product"]["slug"], slug)
        self.assertFalse(context["cross_sells"])
