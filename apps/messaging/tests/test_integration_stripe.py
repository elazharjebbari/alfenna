from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.accounts.models import StudentProfile
from apps.billing.models import Order, OrderStatus
from apps.billing.webhooks import _process_event
from apps.messaging.models import OutboxEmail
from apps.messaging.template_loader import FileSystemTemplateLoader

UserModel = get_user_model()


@override_settings(ROOT_URLCONF="lumierelearning.urls")
class StripeMessagingIntegrationTests(TestCase):
    def setUp(self) -> None:
        self.user = UserModel.objects.create_user(
            username="buyer",
            email="buyer@example.com",
            password="password123",
            first_name="Buyer",
        )
        StudentProfile.objects.get_or_create(user=self.user)
        # Ensure templates are available (data migration should handle it but tests guard).
        FileSystemTemplateLoader().sync()

    def _order(self) -> Order:
        return Order.objects.create(
            user=self.user,
            email=self.user.email,
            currency="EUR",
            amount_subtotal=15000,
            tax_amount=0,
            amount_total=15000,
            idempotency_key="test-order-123",
            status=OrderStatus.PENDING,
        )

    def _event_payload(self, order: Order) -> dict:
        return {
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_test",
                    "payment_method": "pm_test",
                    "latest_charge": "ch_test",
                    "status": "succeeded",
                    "amount_received": order.amount_total,
                    "currency": order.currency.lower(),
                    "metadata": {"order_id": str(order.id)},
                }
            },
        }

    def test_payment_success_known_user_enqueues_invoice_only(self) -> None:
        order = self._order()
        event = self._event_payload(order)

        _process_event(event)

        activations = OutboxEmail.objects.filter(namespace="accounts", purpose="activation", dedup_key=f"order:{order.id}:activation")
        invoices = OutboxEmail.objects.filter(namespace="billing", purpose="invoice_ready", dedup_key=f"order:{order.id}:invoice")

        self.assertEqual(activations.count(), 0)
        self.assertEqual(invoices.count(), 1)

        # Idempotence: replaying the event should not create duplicates.
        _process_event(event)
        self.assertEqual(activations.count(), 0)
        self.assertEqual(invoices.count(), 1)
        invoice_email = invoices.first()
        assert invoice_email is not None
        self.assertIn(str(order.id), invoice_email.rendered_html)

    def test_payment_success_provisions_account_and_sends_activation(self) -> None:
        order = Order.objects.create(
            user=None,
            email="newbuyer@example.com",
            currency="EUR",
            amount_subtotal=25000,
            tax_amount=0,
            amount_total=25000,
            idempotency_key="test-order-456",
            status=OrderStatus.PENDING,
        )

        event = self._event_payload(order)

        _process_event(event)

        order.refresh_from_db()
        new_user = UserModel.objects.get(email="newbuyer@example.com")
        self.assertEqual(order.user, new_user)
        self.assertTrue(new_user.is_active)
        self.assertFalse(new_user.has_usable_password())
        self.assertTrue(StudentProfile.objects.filter(user=new_user).exists())

        activations = OutboxEmail.objects.filter(namespace="accounts", purpose="activation", dedup_key=f"order:{order.id}:activation")
        invoices = OutboxEmail.objects.filter(namespace="billing", purpose="invoice_ready", dedup_key=f"order:{order.id}:invoice")

        self.assertEqual(activations.count(), 1)
        self.assertEqual(invoices.count(), 1)

        _process_event(event)
        self.assertEqual(activations.count(), 1)
        self.assertEqual(invoices.count(), 1)
