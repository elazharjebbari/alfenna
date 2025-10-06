from __future__ import annotations

from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.utils.translation import override
from unittest.mock import patch

from apps.marketing.models.models_pricing import PricePlan

from ..views.views_billing import CheckoutOrchestratorView, ThankYouView


class BillingViewsTests(TestCase):
    def setUp(self) -> None:
        self.plan = PricePlan.objects.create(
            slug="premium-pro",
            title="Premium Pro",
            price_cents=24995,
            old_price_cents=39900,
            is_active=True,
        )
        self.factory = RequestFactory()

    @patch("apps.pages.views.views_billing.response.render_base", return_value=HttpResponse("ok"))
    @patch("apps.pages.views.views_billing.pipeline.collect_page_assets", return_value={})
    @patch("apps.pages.views.views_billing.pipeline.render_slot_fragment", return_value={"html": ""})
    @patch("apps.pages.views.views_billing.pipeline.build_page_spec", return_value={"slots": {}})
    def test_checkout_view_pushes_price_plan_into_pipeline(self, mock_build, *_mocks):
        request = self.factory.get(f"/billing/checkout/plan/{self.plan.slug}/?currency=usd")
        response = CheckoutOrchestratorView.as_view()(request, plan_slug=self.plan.slug)

        self.assertEqual(response.status_code, 200)
        kwargs = mock_build.call_args.kwargs
        extra = kwargs.get("extra", {})
        self.assertEqual(extra.get("price_plan"), self.plan)
        self.assertEqual(extra.get("plan_slug"), self.plan.slug)
        self.assertEqual(extra.get("currency"), "USD")

    @patch("apps.pages.views.views_billing.response.render_base", return_value=HttpResponse("ok"))
    @patch("apps.pages.views.views_billing.pipeline.collect_page_assets", return_value={})
    @patch("apps.pages.views.views_billing.pipeline.render_slot_fragment", return_value={"html": ""})
    @patch("apps.pages.views.views_billing.pipeline.build_page_spec", return_value={"slots": {}})
    def test_thank_you_view_pushes_price_plan(self, mock_build, *_mocks):
        request = self.factory.get(f"/billing/thank-you/plan/{self.plan.slug}/")
        with override("fr"):
            response = ThankYouView.as_view()(request, plan_slug=self.plan.slug)

        self.assertEqual(response.status_code, 200)
        kwargs = mock_build.call_args.kwargs
        extra = kwargs.get("extra", {})
        self.assertEqual(extra.get("price_plan"), self.plan)
        self.assertEqual(extra.get("plan_slug"), self.plan.slug)
