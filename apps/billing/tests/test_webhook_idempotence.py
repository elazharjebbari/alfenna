from django.test import TestCase, override_settings

from apps.billing.models import Order, OrderStatus, WebhookEvent, WebhookEventStatus
from apps.billing.webhooks import _process_event


@override_settings(BILLING_ENABLED=True)
class WebhookIdempotenceTests(TestCase):
    def setUp(self) -> None:
        self.order = Order.objects.create(
            email="buyer@example.com",
            currency="EUR",
            amount_subtotal=1990,
            tax_amount=0,
            amount_total=1990,
            status=OrderStatus.PENDING_PAYMENT,
            stripe_payment_intent_id="pi_test_123",
            metadata={"order_id": "1"},
        )
        # ensure metadata references actual order id for lookup
        self.order.metadata["order_id"] = str(self.order.id)
        self.order.save(update_fields=["metadata"])

    def _payment_succeeded_event(self) -> dict:
        return {
            "id": "evt_test_success",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": self.order.stripe_payment_intent_id,
                    "payment_intent": self.order.stripe_payment_intent_id,
                    "metadata": {"order_id": str(self.order.id)},
                    "amount_received": self.order.amount_total,
                    "currency": self.order.currency,
                }
            },
        }

    def test_replaying_same_event_has_no_side_effect(self) -> None:
        event = self._payment_succeeded_event()

        _process_event(event, correlation_id="test-corr", stripe_signature="sig")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PAID)
        self.assertEqual(WebhookEvent.objects.count(), 1)
        record = WebhookEvent.objects.get()
        self.assertEqual(record.status, WebhookEventStatus.PROCESSED)

        # replay same event
        _process_event(event, correlation_id="test-corr", stripe_signature="sig")
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PAID)
        self.assertEqual(WebhookEvent.objects.count(), 1)
        self.assertEqual(WebhookEvent.objects.get().status, WebhookEventStatus.PROCESSED)
