from __future__ import annotations

import json
import sys
from unittest import mock

from django.test import Client, TestCase, override_settings

from apps.catalog.models import Product

class CheckoutSessionViewTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()

    def test_requires_online_payment_method(self) -> None:
        response = self.client.post(
            "/api/checkout/sessions/",
            data=json.dumps({"payment_method": "cod"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("online", response.json()["detail"])

    @override_settings(STRIPE_SECRET_KEY="")
    def test_returns_mock_redirect_when_no_stripe(self) -> None:
        response = self.client.post(
            "/api/checkout/sessions/",
            data=json.dumps({
                "payment_method": "online",
                "amount_cents": 1500,
                "currency": "mad",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("redirect_url", body)
        self.assertIn("/pay/sandbox/", body["redirect_url"])

    @override_settings(STRIPE_SECRET_KEY="sk_test_xyz")
    def test_uses_stripe_when_configured(self) -> None:
        fake_stripe = mock.Mock()
        fake_session = mock.Mock(url="https://stripe.example/session")
        fake_stripe.checkout.Session.create.return_value = fake_session

        with mock.patch.dict(sys.modules, {"stripe": fake_stripe}):
            response = self.client.post(
                "/api/checkout/sessions/",
                data=json.dumps({"payment_method": "online", "amount_minor": 1234}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["redirect_url"], "https://stripe.example/session")
        fake_stripe.checkout.Session.create.assert_called_once()


class CheckoutSessionAmountTests(TestCase):
    fixtures = ["products_pack_cosmetique.json"]

    def setUp(self) -> None:
        self.client = Client()

    def test_online_payment_uses_promo_price_and_discount(self) -> None:
        product = Product.objects.get(slug="pack-cosmetique-naturel")
        expected_minor = int(29900 * 2 - 2000)

        with mock.patch("apps.checkout.views._create_stripe_session") as mocked_checkout:
            mocked_checkout.return_value = "https://checkout.example/mock"
            response = self.client.post(
                "/api/checkout/sessions/",
                data=json.dumps(
                    {
                        "payment_method": "online",
                        "product_id": product.id,
                        "quantity": 2,
                        "online_discount_minor": 999999,
                        "currency": "mad",
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200, response.content)
        mocked_checkout.assert_called_once()
        payload = mocked_checkout.call_args[0][0]
        self.assertEqual(payload.get("amount_minor"), expected_minor)
        self.assertEqual(payload.get("amount_cents"), expected_minor)
        self.assertEqual(payload.get("currency"), "MAD")
        self.assertEqual(payload.get("product_name"), product.name)
        self.assertEqual(payload.get("online_discount_minor"), 2000)
        self.assertIn("@example.invalid", payload.get("email", ""))
