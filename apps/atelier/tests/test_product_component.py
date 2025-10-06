from __future__ import annotations

from django.test import RequestFactory, SimpleTestCase

from apps.atelier.compose.hydrators.product.product import hydrate_product


class ProductHydratorTests(SimpleTestCase):
    factory = RequestFactory()

    def _request(self):
        request = self.factory.get("/produits/")
        request.site_version = "core"
        return request

    def test_hydrate_product_defaults_resolve_three_step_form(self) -> None:
        params = {
            "product": {"id": "demo", "name": "Produit demo"},
            "media": {"images": [{"src": "https://placehold.co/800x600", "alt": "Visuel"}]},
        }
        ctx = hydrate_product(self._request(), params)

        self.assertEqual(ctx["product"]["id"], "demo")
        self.assertEqual(ctx["product"]["name"], "Produit demo")
        self.assertTrue(ctx["media"]["images"])
        self.assertTrue(
            ctx["form"]["template"].endswith("components/core/forms/lead_step3/lead_step3.html")
        )
        self.assertTrue(ctx["tracking"]["enabled"])

    def test_custom_action_url_passthrough(self) -> None:
        params = {
            "product": {"id": "demo", "name": "Produit demo"},
            "media": {"images": []},
            "form": {
                "alias": "core/forms/lead_step2",
                "action_url": "/leads/custom-submit/",
                "fields_map": {"fullname": "fname", "phone": "phone"},
            },
            "tracking": {"enabled": False},
        }
        ctx = hydrate_product(self._request(), params)
        self.assertEqual(ctx["form"]["action_url"], "/leads/custom-submit/")
        self.assertFalse(ctx["tracking"]["enabled"])
        self.assertTrue(ctx["form"]["template"].endswith("components/core/forms/lead_step2/lead_step2.html"))

    def test_reverse_action_url(self) -> None:
        params = {
            "product": {"id": "demo", "name": "Produit demo"},
            "media": {"images": []},
            "form": {"action_url": "pages:home"},
        }
        ctx = hydrate_product(self._request(), params)
        self.assertEqual(ctx["form"]["action_url"], "/")

    def test_media_fallback_injects_placeholders(self) -> None:
        params = {
            "product": {"id": "demo", "name": "Produit demo"},
            "media": {"images": []},
        }
        ctx = hydrate_product(self._request(), params)
        images = ctx["media"]["images"]
        self.assertEqual(len(images), 3)
        for idx, item in enumerate(images):
            self.assertEqual(item["index"], idx)
            self.assertIn("src", item)
            self.assertIn("thumb", item)
            self.assertTrue(item["src"])
            self.assertTrue(item["thumb"])

    def test_lead_step3_alias_resolves_template(self) -> None:
        params = {
            "product": {"id": "demo", "name": "Produit demo"},
            "media": {"images": []},
            "form": {"alias": "core/forms/lead_step3"},
        }
        ctx = hydrate_product(self._request(), params)
        template_path = ctx["form"].get("template")
        self.assertIsNotNone(template_path)
        self.assertTrue(
            str(template_path).endswith("components/core/forms/lead_step3/lead_step3.html")
        )
