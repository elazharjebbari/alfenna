from decimal import Decimal

from django.test import TestCase

from apps.marketing.models.models_pricing import PricePlan

from ..services.pricing import PriceService


class PriceServicePlanTests(TestCase):
    def setUp(self) -> None:
        self.plan = PricePlan.objects.create(
            slug="premium-pro",
            title="Premium Pro",
            price_cents=24995,
            old_price_cents=39900,
            is_active=True,
        )

    def test_compute_total_from_plan_returns_expected_amounts(self) -> None:
        totals = PriceService.compute_total_from_plan(self.plan, "eur")

        self.assertEqual(totals["currency"], "EUR")
        self.assertEqual(totals["amount_subtotal"], 24995)
        self.assertEqual(totals["amount_total"], 24995)
        self.assertEqual(totals["list_price_cents"], 39900)
        self.assertEqual(totals["coupon"], "")
        self.assertEqual(totals["final_amount_cents"], 24995)
        self.assertEqual(totals["discount_pct"], Decimal("37.36"))
