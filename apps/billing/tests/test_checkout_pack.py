from __future__ import annotations

import json
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.billing.models import Order
from apps.billing.services import compute_pack_totals
from apps.catalog.models.models import Product, ProductOffer
from apps.catalog.models.models_crosssell import ComplementaryProduct, ProductCrossSell


@override_settings(BILLING_ENABLED=True, STRIPE_SECRET_KEY="", STRIPE_PUBLISHABLE_KEY="pk_test_pack")
class CheckoutPackTests(TestCase):
    def setUp(self) -> None:
        self.product = Product.objects.create(
            slug="rituel-naturel",
            name="Rituel naturel",
            currency="MAD",
            extra={"online_discount_amount": "20"},
        )
        self.offer_solo = ProductOffer.objects.create(
            product=self.product,
            code="solo",
            title="Pack Solo",
            price=Decimal("349.00"),
            compare_at_price=Decimal("399.00"),
            position=0,
            extra={"pack_slug": "solo"},
        )
        self.offer_duo = ProductOffer.objects.create(
            product=self.product,
            code="duo",
            title="Pack Duo",
            price=Decimal("489.00"),
            compare_at_price=Decimal("558.00"),
            position=1,
            is_featured=True,
            extra={"pack_slug": "duo"},
        )
        self.complementary = ComplementaryProduct.objects.create(
            slug="bougie-massage",
            title="Bougie massage",
            price=Decimal("99.00"),
            currency="MAD",
        )
        ProductCrossSell.objects.create(
            product=self.product,
            complementary=self.complementary,
            position=0,
        )

    def test_compute_pack_totals_with_complementary(self) -> None:
        totals = compute_pack_totals(
            product_slug=self.product.slug,
            pack_slug="duo",
            complementary_slugs=[self.complementary.slug],
            payment_mode="online",
        )
        self.assertEqual(totals.subtotal, 48900 + 9900)
        self.assertEqual(totals.discount, 2000)
        self.assertEqual(totals.total, 48900 + 9900 - 2000)
        self.assertEqual(totals.pack.slug, "duo")

    def test_preview_pack_totals_endpoint(self) -> None:
        url = reverse("billing:preview_totals")
        payload = {
            "product_slug": self.product.slug,
            "pack_slug": "solo",
            "complementary_slugs": [],
            "payment_mode": "online",
        }
        response = self.client.post(url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["subtotal"], 34900)
        self.assertEqual(data["discount"], 2000)
        self.assertEqual(data["total"], 32900)
        self.assertEqual(data["currency"], "MAD")

        payload["payment_mode"] = "cod"
        response = self.client.post(url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["discount"], 0)

    def test_create_payment_intent_for_pack(self) -> None:
        url = reverse("billing:create_payment_intent")
        payload = {
            "checkout_kind": "pack",
            "product_slug": self.product.slug,
            "pack_slug": "duo",
            "complementary_slugs": [self.complementary.slug],
            "payment_mode": "online",
            "currency": "MAD",
            "email": "buyer@example.com",
            "ff_session_key": "session-123",
        }

        response = self.client.post(url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("clientSecret", data)
        self.assertEqual(data["subtotal"], 48900 + 9900)
        self.assertEqual(data["discount"], 2000)
        self.assertEqual(data["total"], 48900 + 9900 - 2000)
        self.assertEqual(data["pack"]["slug"], "duo")

        order = Order.objects.get(id=data["orderId"])
        self.assertEqual(order.amount_total, data["total"])
        self.assertEqual(order.metadata.get("pack_slug"), "duo")
        self.assertEqual(order.metadata.get("checkout_kind"), "pack")
        self.assertEqual(order.metadata.get("ff_session_key"), "session-123")
        item_skus = list(order.items.values_list("product_sku", flat=True))
        self.assertIn("pack:rituel-naturel:duo", item_skus)
        self.assertIn("complementary:bougie-massage", item_skus)
