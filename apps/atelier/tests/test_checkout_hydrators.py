from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.test import RequestFactory, TestCase

from apps.atelier.compose.hydrators.checkout.hydrators import (
    hydrate_order_summary,
    hydrate_payment_form,
    hydrate_legal_info,
)
from apps.marketing.models.models_pricing import PriceFeature, PricePlan


class OrderSummaryHydratorTests(TestCase):
    def setUp(self) -> None:
        self.request_factory = RequestFactory()
        self.plan = PricePlan.objects.create(
            slug="pro",
            title="Programme Pro",
            currency="EUR",
            currency_symbol="€",
            price_cents=12900,
            old_price_cents=19900,
            ribbon_label="Best-seller",
        )
        for idx in range(1, 7):
            PriceFeature.objects.create(plan=self.plan, label=f"Avantage {idx}", included=True)

    def test_order_summary_calculates_savings_and_daily_cost(self) -> None:
        request = self.request_factory.get("/billing/checkout/plan/pro/")
        ctx = hydrate_order_summary(
            request,
            {
                "price_plan": self.plan,
                "currency": "EUR",
                "amount_total_cents": 12900,
                "list_price_cents": 19900,
                "discount_pct": Decimal("35.18"),
                "features_primary_limit": 4,
            },
        )

        self.assertEqual(ctx["display_price"], "129.00 EUR")
        self.assertTrue(ctx["show_economy"])
        self.assertEqual(ctx["savings_display"], "70.00 EUR")
        self.assertEqual(ctx["savings_percent_display"], "35.2%")
        self.assertTrue(ctx["show_daily"])
        self.assertIn("EUR / jour", ctx["daily_display"])
        self.assertEqual(len(ctx["primary_features"]), 4)
        self.assertEqual(len(ctx["extra_features"]), 2)
        self.assertIsNone(ctx["order_bump"])

    def test_order_summary_defaults_and_param_overrides(self) -> None:
        request = self.request_factory.get("/billing/checkout/plan/pro/", {"country": "fr"})
        ctx = hydrate_order_summary(
            request,
            {
                "price_plan": self.plan,
                "currency": "EUR",
                "features_primary_limit": 3,
                "features_more_label": "Voir plus",
                "show_daily_approx": False,
                "show_economy": False,
            },
        )

        self.assertEqual(ctx["display_price"], "129.00 EUR")
        self.assertEqual(ctx["list_price_display"], "199.00 EUR")
        self.assertFalse(ctx["show_daily"])
        self.assertFalse(ctx["show_economy"])
        self.assertEqual(len(ctx["primary_features"]), 3)
        self.assertEqual(len(ctx["extra_features"]), 3)
        self.assertTrue(ctx["has_extra_features"])
        self.assertEqual(ctx["features_more_label"], "Voir plus")
        self.assertEqual(ctx["country"], "FR")


class PaymentFormHydratorTests(TestCase):
    def setUp(self) -> None:
        self.request_factory = RequestFactory()
        self.plan = PricePlan.objects.create(
            slug="starter-test",
            title="Starter",
            currency="EUR",
            currency_symbol="€",
            price_cents=8900,
        )

    def test_payment_form_defaults_expose_ui_flags(self) -> None:
        request = self.request_factory.get("/billing/checkout/plan/starter/")
        ctx = hydrate_payment_form(
            request,
            {
                "price_plan": self.plan,
                "currency": "EUR",
            },
        )

        self.assertEqual(ctx["plan_slug"], "starter-test")
        self.assertEqual(ctx["currency"], "EUR")
        self.assertEqual(ctx["amount_total"].quantize(Decimal("0.01")), Decimal("89.00"))
        self.assertTrue(ctx["show_coupon_link"])
        self.assertEqual(ctx["coupon_label"], "Code promo")
        self.assertEqual(ctx["coupon_placeholder"], "ENTRERMONCODE")
        self.assertFalse(ctx["submit_state"])
        self.assertEqual(ctx["cta_label"], "Payer et accéder maintenant")
        self.assertEqual(ctx["stripe_publishable_key"], settings.STRIPE_PUBLISHABLE_KEY)

    def test_payment_form_params_override_defaults(self) -> None:
        request = self.request_factory.get("/billing/checkout/plan/starter/")
        ctx = hydrate_payment_form(
            request,
            {
                "price_plan": self.plan,
                "currency": "EUR",
                "show_coupon_link": False,
                "coupon_label": "Bon d’achat",
                "coupon_placeholder": "MONBONUS",
                "cta_label": "Valider mon accès",
            },
        )

        self.assertFalse(ctx["show_coupon_link"])
        self.assertEqual(ctx["coupon_label"], "Bon d’achat")
        self.assertEqual(ctx["coupon_placeholder"], "MONBONUS")
        self.assertEqual(ctx["cta_label"], "Valider mon accès")


class LegalInfoHydratorTests(TestCase):
    def setUp(self) -> None:
        self.request_factory = RequestFactory()
        self.plan = PricePlan.objects.create(
            slug="legal-plan",
            title="Plan Legal",
            currency="EUR",
            currency_symbol="€",
            price_cents=4900,
        )

    def test_legal_info_defaults_include_faq_and_points(self) -> None:
        request = self.request_factory.get("/billing/checkout/plan/legal-plan/")
        ctx = hydrate_legal_info(
            request,
            {
                "price_plan": self.plan,
                "currency": "EUR",
            },
        )

        self.assertTrue(ctx["security_badges"])
        self.assertGreaterEqual(len(ctx["compact_points"]), 3)
        self.assertEqual(ctx["faq_heading"], "Questions fréquentes")
        self.assertEqual(len(ctx["faq_items"]), 3)
        self.assertTrue(any(link["href"].startswith("/cgv") for link in ctx["legal_links"]))

    def test_legal_info_params_override_defaults(self) -> None:
        request = self.request_factory.get("/billing/checkout/plan/legal-plan/")
        ctx = hydrate_legal_info(
            request,
            {
                "price_plan": self.plan,
                "currency": "EUR",
                "compact": False,
                "compact_points": [
                    {"icon": "star", "text": "Point personnalisé"},
                ],
                "faq_heading": "FAQ checkout",
                "faq_items": [
                    {"question": "Q?", "answer": "R."},
                ],
                "legal_links": [{"label": "CGV", "href": "/cgv/"}],
            },
        )

        self.assertFalse(ctx["compact"])
        self.assertEqual(len(ctx["compact_points"]), 1)
        self.assertEqual(ctx["compact_points"][0]["text"], "Point personnalisé")
        self.assertEqual(ctx["faq_heading"], "FAQ checkout")
        self.assertEqual(len(ctx["faq_items"]), 1)
