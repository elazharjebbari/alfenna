import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.billing.models import Entitlement, Order, OrderStatus
from apps.billing.services import get_order_service
from apps.billing.webhooks import _process_event
from apps.catalog.models.models import Course
from apps.marketing.models.models_pricing import PricePlan


@override_settings(BILLING_ENABLED=True, STRIPE_SECRET_KEY="", STRIPE_PUBLISHABLE_KEY="pk_test_checkout")
class CheckoutFlowTests(TestCase):
    def setUp(self) -> None:
        self.plan = PricePlan.objects.create(
            slug="checkout-plan",
            title="Checkout Plan",
            price_cents=12900,
            is_active=True,
        )
        self.course = Course.objects.create(
            title="Pack premium",
            slug="pack-premium",
            description="",
            is_published=True,
        )
        self.url = reverse("billing:create_payment_intent")

    def _payment_event(self, order: Order) -> dict:
        return {
            "id": f"evt_{order.id}",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": order.stripe_payment_intent_id,
                    "payment_intent": order.stripe_payment_intent_id,
                    "amount_received": order.amount_total,
                    "currency": order.currency,
                    "metadata": {"order_id": str(order.id)},
                }
            },
        }

    def test_guest_checkout_creates_guest_profile_and_allows_merge(self) -> None:
        guest_id = "guest-123"
        payload = {
            "plan_slug": self.plan.slug,
            "email": "guest@example.com",
            "currency": "EUR",
            "guest_id": guest_id,
            "course_id": self.course.id,
        }

        response = self.client.post(self.url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        order = Order.objects.get(id=response.json()["orderId"])
        self.assertEqual(order.status, OrderStatus.PENDING_PAYMENT)
        self.assertEqual(order.metadata.get("guest_id"), guest_id)

        _process_event(self._payment_event(order), correlation_id="corr-guest", stripe_signature="sig")
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.PAID)
        self.assertIsNotNone(order.customer_profile)
        self.assertEqual(order.customer_profile.guest_id, guest_id)
        self.assertIsNone(order.customer_profile.user)

        # Simulate later merge when user account is created
        user = get_user_model().objects.create_user(
            username="guest-user",
            email=order.email,
            password="pass1234",
        )
        order.user = user
        order.save(update_fields=["user"])
        profile = get_order_service().ensure_customer_profile(
            email=order.email,
            user=user,
            guest_id=guest_id,
            stripe_customer_id=order.stripe_customer_id or None,
        )
        profile.refresh_from_db()
        self.assertEqual(profile.user, user)
        self.assertEqual(profile.merged_from_guest_id, guest_id)

    def test_logged_checkout_links_profile_to_user(self) -> None:
        user = get_user_model().objects.create_user(
            username="buyer",
            email="buyer@example.com",
            password="pass1234",
        )
        self.client.force_login(user)
        payload = {
            "plan_slug": self.plan.slug,
            "email": user.email,
            "currency": "EUR",
            "course_id": self.course.id,
        }
        response = self.client.post(self.url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        order = Order.objects.get(id=response.json()["orderId"])

        _process_event(self._payment_event(order), correlation_id="corr-logged", stripe_signature="sig")
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.PAID)
        self.assertEqual(order.user, user)
        self.assertIsNotNone(order.customer_profile)
        self.assertEqual(order.customer_profile.user, user)

        self.assertTrue(Entitlement.objects.filter(user=user, course=self.course).exists())
