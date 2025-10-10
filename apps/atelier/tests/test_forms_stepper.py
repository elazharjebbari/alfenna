from __future__ import annotations

import json

from django.template.loader import render_to_string
from django.test import SimpleTestCase


class LeadStepperTemplateTests(SimpleTestCase):
    base_context = {
        "action_url": "/leads/collect/",
        "fields_map": {
            "fullname": "full_name",
            "phone": "phone_number",
            "address": "address",
            "quantity": "quantity",
            "offer": "offer_key",
            "product": "product",
            "promotion": "promotion_selected",
        },
        "product": {
            "id": "sku-1",
            "slug": "sku-1",
            "name": "Produit Test",
            "description": "Description test",
        },
        "pricing": {"promo_price": 199, "price": 249, "currency": "MAD"},
    }

    def test_lead_step3_template_renders(self) -> None:
        html = render_to_string(
            "components/core/forms/lead_step3/lead_step3.html",
            context=self.base_context,
        )
        self.assertIn('data-ff-root', html)
        self.assertIn('data-ff-step="2"', html)
        self.assertIn('class="form-control"', html)
        self.assertIn('btn af-cta', html)

    def test_step3_template_has_thank_you_step(self) -> None:
        html = render_to_string(
            "components/core/forms/lead_step3/lead_step3.html",
            context=self.base_context,
        )
        self.assertIn('data-ff-root', html)
        self.assertIn('data-steps="4"', html)
        self.assertIn('data-checkout-url="/api/checkout/sessions/"', html)
        self.assertIn('data-ff-step="3"', html)
        self.assertIn('data-ff-step="4"', html)
        self.assertIn('Paiement', html)
        self.assertIn('Merci, votre commande est enregistrée.', html)

    def test_landingpage_template_is_minimal(self) -> None:
        context = {
            "action_url": "/api/leads/collect/",
            "fields_map": {
                "fullname": "full_name",
                "phone": "phone_number",
                "city": "city",
                "email": "email",
                "payment_mode": "payment_mode",
                "pack_slug": "pack_slug",
                "complementary_slugs": "context.complementary_slugs",
                "product": "product",
                "currency": "currency",
            },
            "product": {"id": "sku-landing", "slug": "sku-landing"},
            "pricing": {"currency": "MAD"},
            "form": {
                "flow_key": "landing_short_flow",
                "offers": [
                    {"code": "duo", "slug": "duo", "title": "Pack Duo", "price": 299},
                    {"code": "solo", "slug": "solo", "title": "Pack Solo", "price": 199},
                ],
                "bump": {"slug": "bump_extra", "title": "Supplément"},
                "flow_config_json": json.dumps({
                    "flow_key": "landing_short_flow",
                    "endpoint_url": "/api/leads/collect/",
                }),
            },
        }

        html = render_to_string(
            "components/core/forms/form_landingpage/form_landingpage.html",
            context=context,
        )

        self.assertIn('data-ff-root', html)
        self.assertIn('data-ff-step="2"', html)
        self.assertIn('Paiement à la livraison', html)
        self.assertIn('data-ff-payment-hidden', html)
        self.assertIn('data-ff-config', html)
