from __future__ import annotations

import json
from decimal import Decimal

from django.test import RequestFactory, TestCase

from apps.atelier.compose.hydrators.product.product import hydrate_product
from apps.catalog.models import (
    Product as CatalogProduct,
    ProductBadge,
    ProductImage,
    ProductOffer,
    ProductOption,
)


class ProductHydratorTests(TestCase):
    factory = RequestFactory()

    def _request(self, path: str = "/produits/"):
        request = self.factory.get(path, {"utm_source": "meta"})
        request.site_version = "core"
        return request

    def _create_product(self) -> CatalogProduct:
        product = CatalogProduct.objects.create(
            slug="huile-argan",
            name="Huile d'argan premium",
            description="Flacon 50ml pressé à froid",
            price=Decimal("399"),
            promo_price=Decimal("349"),
            currency="MAD",
        )
        ProductBadge.objects.create(product=product, text="100% bio", icon="fa-leaf")
        ProductImage.objects.create(
            product=product,
            src="https://example.com/argan-front.jpg",
            thumb="https://example.com/argan-thumb.jpg",
            position=0,
        )
        ProductOption.objects.create(
            product=product,
            key="color",
            label="Couleur",
            items=[{"key": "ambre", "label": "Ambrée"}],
            position=0,
        )
        ProductOffer.objects.create(
            product=product,
            code="solo",
            title="Pack Solo",
            price=Decimal("349"),
            compare_at_price=Decimal("399"),
            is_featured=True,
            savings_label="-50 MAD",
            position=0,
        )
        ProductOffer.objects.create(
            product=product,
            code="duo",
            title="Pack Duo",
            price=Decimal("489"),
            compare_at_price=Decimal("698"),
            savings_label="Éco 209 MAD",
            position=1,
        )
        return product

    def test_hydrate_product_merges_db_and_config_overrides(self) -> None:
        product = self._create_product()
        params = {
            "product_slug": product.slug,
            "product": {"description": "Edition limitée"},
            "form": {
                "alias": "core/forms/lead_step3",
                "fields_map": {"fullname": "full_name", "phone": "phone"},
                "ui_texts": {
                    "bullets": ["Livraison 24 h", "Paiement sécurisé"],
                    "social_proof": "+ 1 200 clientes",
                    "online_discount_amount": 30,
                    "payment_labels": {"online": "Carte bancaire", "cod": "Paiement à la livraison"},
                },
                "offers": [
                    {"code": "solo", "title": "Pack Solo +", "price": 329},
                ],
                "bump": {
                    "enabled": True,
                    "label": "+ Sérum capillaire", "price": 59,
                },
            },
        }

        ctx = hydrate_product(self._request(f"/produits/{product.slug}/"), params)

        self.assertEqual(ctx["product"]["name"], "Huile d'argan premium")
        self.assertEqual(ctx["product"]["description"], "Edition limitée")
        self.assertTrue(ctx["media"]["images"])
        self.assertEqual(ctx["media"]["images"][0]["src"], "https://example.com/argan-front.jpg")
        self.assertIn("color", ctx["options"])
        self.assertEqual(ctx["options"]["color"]["items"][0]["label"], "Ambrée")
        self.assertTrue(ctx["pricing"]["has_promo"])
        self.assertEqual(ctx["pricing"]["savings"], Decimal("50"))

        offers = ctx["form"]["offers"]
        self.assertEqual(offers[0]["code"], "solo")
        self.assertEqual(offers[0]["title"], "Pack Solo +")
        self.assertEqual(offers[0]["price"], Decimal("329"))
        self.assertEqual(offers[1]["code"], "duo")
        self.assertEqual(ctx["form"]["bump"]["price"], 59)

        ui_texts = ctx["form"]["ui_texts"]
        self.assertIn("bullets", ui_texts)
        self.assertEqual(ui_texts["social_proof"], "+ 1 200 clientes")
        self.assertEqual(ui_texts["online_discount_amount"], 30)

    def test_hydrate_product_without_db_uses_placeholders(self) -> None:
        params = {
            "product": {"id": "demo", "name": "Produit demo"},
            "media": {"images": []},
        }
        ctx = hydrate_product(self._request(), params)
        images = ctx["media"]["images"]
        self.assertEqual(len(images), 3)
        for index, item in enumerate(images):
            self.assertEqual(item["index"], index)
            self.assertTrue(item["src"].startswith("data:image/svg+xml;base64"))

    def test_flow_config_contains_fields_map(self) -> None:
        product = self._create_product()
        params = {
            "product_slug": product.slug,
            "form": {
                "fields_map": {
                    "fullname": "firstname",
                    "phone": "mobile",
                    "payment_method": "payment",
                }
            },
        }
        ctx = hydrate_product(self._request(), params)
        flow_config = json.loads(ctx["form"]["flow_config_json"])
        self.assertIn("fields_map", flow_config)
        self.assertEqual(flow_config["fields_map"]["phone"], "mobile")

    def test_form_alias_resolution(self) -> None:
        params = {
            "product": {"id": "demo", "name": "Produit demo"},
            "media": {"images": []},
            "form": {"alias": "core/forms/lead_step3"},
        }
        ctx = hydrate_product(self._request(), params)
        template_path = ctx["form"].get("template")
        self.assertIsNotNone(template_path)
        self.assertTrue(str(template_path).endswith("components/core/forms/lead_step3/lead_step3.html"))

    def test_form_landingpage_alias_resolution(self) -> None:
        product = self._create_product()
        params = {
            "product_slug": product.slug,
            "form": {
                "alias": "core/forms/form_landingpage",
                "fields_map": {
                    "fullname": "full_name",
                    "phone": "phone_number",
                    "city": "city",
                    "email": "email",
                    "payment_mode": "payment_mode",
                    "pack_slug": "pack_slug",
                },
            },
        }
        ctx = hydrate_product(self._request(f"/produits/{product.slug}/v2/"), params)
        template_path = ctx["form"].get("template")
        self.assertIsNotNone(template_path)
        self.assertTrue(str(template_path).endswith("components/core/forms/form_landingpage/form_landingpage.html"))
