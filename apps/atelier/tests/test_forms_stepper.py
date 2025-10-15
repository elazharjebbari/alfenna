from __future__ import annotations

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
        "product": {"id": "sku-1"},
        "pricing": {"promo_price": 199, "price": 249},
    }

    def test_step2_template_renders_bootstrap_classes(self) -> None:
        html = render_to_string(
            "components/core/forms/lead_step2/lead_step2.html",
            context=self.base_context,
        )
        self.assertIn('data-form-stepper', html)
        self.assertIn('data-steps="2"', html)
        self.assertIn('class="form-control"', html)
        self.assertIn('btn btn-primary', html)

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
