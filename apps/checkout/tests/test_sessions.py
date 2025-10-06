from __future__ import annotations

import json
import sys
from unittest import mock

from django.test import Client, TestCase, override_settings


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

    def test_returns_mock_redirect_when_no_stripe(self) -> None:
        response = self.client.post(
            "/api/checkout/sessions/",
            data=json.dumps({"payment_method": "online"}),
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
