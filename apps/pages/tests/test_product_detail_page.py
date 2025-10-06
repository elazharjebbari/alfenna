from __future__ import annotations

from django.test import TestCase


class ProductDetailPageTests(TestCase):
    def test_product_detail_route_returns_ok(self) -> None:
        response = self.client.get("/produits/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("data-cmp=\"product\"", html)
        self.assertIn("data-form-stepper", html)
        self.assertIn('data-steps="3"', html)
        self.assertIn("Merci, votre commande est enregistree.", html)
        steps_count = html.count("data-step=\"")
        self.assertGreaterEqual(steps_count, 3)
        self.assertIn('data-action-url="/api/leads/collect/"', html)
        self.assertIn('data-sign-url="/api/leads/sign/"', html)
        self.assertIn('data-require-signed="true"', html)
        self.assertIn('data-fields-map=\'{"fullname":"full_name"', html)
