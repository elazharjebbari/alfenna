from __future__ import annotations

from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase, override_settings

from apps.atelier.compose.hydrators.product.product import hydrate_product
from apps.catalog.models import Product


@override_settings(LANGUAGE_CODE="fr")
class ProductPageIntegrationTest(TestCase):
    fixtures = ["products_pack_cosmetique.json"]

    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.request = self.factory.get("/produits/pack-cosmetique-naturel/")

    def test_product_component_renders_from_db(self) -> None:
        product = Product.objects.get(slug="pack-cosmetique-naturel")
        context = hydrate_product(
            self.request,
            params={
                "product": {"id": product.id},
                "form": {"alias": "core/forms/lead_step3", "fields_map": {}},
                "media": {"lightbox": True},
            },
        )

        html = render_to_string("components/core/product/hero.html", context)
        if "Pack Cosmétique Naturel" not in html:
            print("\n---- DEBUG HTML ----\n", html[:2000], "\n---------------------")

        self.assertIn("Pack Cosmétique Naturel", html)
        self.assertRegex(html, r"299\s*MAD")
        self.assertRegex(html, r"349\s*MAD")
        self.assertIn("100% naturel", html)
        self.assertIn("Pack cosmétique — visuel 1", html)
        self.assertIn("Couleur", html)
        self.assertIn("Rose poudré", html)
        self.assertIn("+ Bougie de massage hydratante", html)
        self.assertIn("Paiement", html)
        self.assertIn('data-unit-price="299', html)
        self.assertIn('data-online-discount="20', html)

    def test_product_component_falls_back_to_config_when_missing(self) -> None:
        request = self.factory.get("/produits/")
        context = hydrate_product(
            request,
            params={
                "lookup": {"slug": "{{ url.kwargs.product_slug }}"},
                "product": {"name": "Produit Config Fallback", "slug": "fallback"},
                "form": {"alias": "core/forms/lead_step3"},
            },
        )

        html = render_to_string("components/core/product/hero.html", context)
        self.assertIn("Produit Config Fallback", html)
        self.assertIn("data-cmp=\"product\"", html)
