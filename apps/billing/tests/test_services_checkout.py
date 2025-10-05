import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.catalog.models.models import Course
from apps.marketing.models.models_pricing import PricePlan

from ..models import Entitlement, Order
from ..services import EntitlementService, PaymentService


class PaymentServiceCheckoutTests(TestCase):
    @override_settings(STRIPE_SECRET_KEY="", STRIPE_PUBLISHABLE_KEY="pk_test_123", BILLING_ENABLED=True)
    def test_create_order_with_price_plan_freezes_plan_data(self) -> None:
        plan = PricePlan.objects.create(
            slug="essentiel",
            title="Essentiel",
            price_cents=14995,
            old_price_cents=24995,
            is_active=True,
        )
        user = get_user_model().objects.create_user(
            username="planbuyer",
            email="buyer@example.com",
            password="pass1234",
        )

        order, payload = PaymentService.create_or_update_order_and_intent(
            user=user,
            email=user.email,
            price_plan=plan,
            currency="eur",
        )

        order.refresh_from_db()
        self.assertEqual(order.price_plan, plan)
        self.assertEqual(order.pricing_code, plan.slug)
        self.assertEqual(order.list_price_cents, 24995)
        expected_discount = ((Decimal(plan.old_price_cents) - Decimal(plan.price_cents)) / Decimal(plan.old_price_cents) * Decimal("100")).quantize(Decimal("0.01"))
        self.assertEqual(order.discount_pct_effective, expected_discount)
        self.assertEqual(order.amount_total, 14995)
        self.assertEqual(order.currency, "EUR")
        self.assertTrue(order.idempotency_key)

        self.assertIn("client_secret", payload)
        self.assertTrue(payload["client_secret"].startswith("cs_test_"))
        self.assertEqual(payload["publishable_key"], "pk_test_123")

    @override_settings(STRIPE_SECRET_KEY="", STRIPE_PUBLISHABLE_KEY="pk_test_123", BILLING_ENABLED=True)
    def test_plan_checkout_with_course_assigns_course_to_order(self) -> None:
        plan = PricePlan.objects.create(
            slug="starter-plan",
            title="Starter",
            price_cents=9900,
            is_active=True,
        )
        course = Course.objects.create(
            title="Bougies naturelles",
            slug="bougies-naturelles-test",
            description="",
            is_published=True,
        )

        payload = {
            "plan_slug": plan.slug,
            "email": "buyer@example.com",
            "currency": "EUR",
            "course_id": course.id,
        }

        response = self.client.post(
            reverse("billing:create_payment_intent"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        order_id = response.json()["orderId"]
        order = Order.objects.get(id=order_id)
        self.assertEqual(order.course_id, course.id)

    @override_settings(STRIPE_SECRET_KEY="", STRIPE_PUBLISHABLE_KEY="pk_test_123", BILLING_ENABLED=True)
    def test_entitlement_created_for_plan_order_with_course(self) -> None:
        plan = PricePlan.objects.create(
            slug="createur-test",
            title="Createur",
            price_cents=19900,
            is_active=True,
        )
        course = Course.objects.create(
            title="Bougies naturelles",
            slug="bougies-naturelles-premium",
            description="",
            is_published=True,
        )
        user = get_user_model().objects.create_user(
            username="entitled",
            email="entitled@example.com",
            password="pass1234",
        )

        order, _ = PaymentService.create_or_update_order_and_intent(
            user=user,
            email=user.email,
            price_plan=plan,
            course=course,
            currency="EUR",
        )

        EntitlementService.grant_entitlement(order, "payment_intent.succeeded", {"data": {"object": {}}})

        self.assertTrue(Entitlement.objects.filter(user=user, course=course).exists())

    @override_settings(STRIPE_SECRET_KEY="", STRIPE_PUBLISHABLE_KEY="pk_test_123", BILLING_ENABLED=True)
    def test_payment_intent_idempotency_reuses_existing_intent(self) -> None:
        plan = PricePlan.objects.create(
            slug="unique-plan",
            title="Unique",
            price_cents=12900,
            is_active=True,
        )
        user = get_user_model().objects.create_user(
            username="idempotent",
            email="idempotent@example.com",
            password="pass1234",
        )

        order, payload = PaymentService.create_or_update_order_and_intent(
            user=user,
            email=user.email,
            price_plan=plan,
            currency="EUR",
        )

        order.refresh_from_db()
        _, payload_again = PaymentService.create_or_update_order_and_intent(
            user=user,
            email=user.email,
            price_plan=plan,
            currency="EUR",
            existing_order=order,
        )

        self.assertEqual(payload["client_secret"], payload_again["client_secret"])
        order.refresh_from_db()
        self.assertEqual(order.payment_attempts.count(), 1)
