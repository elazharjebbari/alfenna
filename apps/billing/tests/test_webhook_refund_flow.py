from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.billing.models import Order, OrderStatus, Refund, RefundStatus
from apps.billing.services.refund import RefundService
from apps.billing.webhooks import _process_event
from apps.messaging.models import OutboxEmail


@override_settings(BILLING_ENABLED=True, STRIPE_SECRET_KEY="", STRIPE_PUBLISHABLE_KEY="pk_test_refund", STRIPE_WEBHOOK_SECRET="")
class RefundFlowTests(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="buyer",
            email="buyer@example.com",
            password="pass1234",
        )
        self.order = Order.objects.create(
            user=self.user,
            email=self.user.email,
            currency="EUR",
            amount_subtotal=5000,
            tax_amount=0,
            amount_total=5000,
            status=OrderStatus.PAID,
            stripe_payment_intent_id="pi_refund_123",
            metadata={"order_id": "1"},
        )
        self.order.metadata["order_id"] = str(self.order.id)
        self.order.save(update_fields=["metadata"])

    def _refund_event(self, refund_id: str, amount: int) -> dict:
        return {
            "id": "evt_refund",
            "type": "charge.refunded",
            "data": {
                "object": {
                    "id": refund_id,
                    "payment_intent": self.order.stripe_payment_intent_id,
                    "amount": amount,
                    "metadata": {"order_id": str(self.order.id)},
                }
            },
        }

    def test_refund_service_and_webhook_transition_order(self) -> None:
        refund_service = RefundService()
        result = refund_service.initiate(self.order, amount=2500)
        self.assertIsInstance(result.payload, dict)

        event = self._refund_event(result.refund.refund_id, 2500)
        _process_event(event, correlation_id="corr-refund", stripe_signature="sig")

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.REFUNDED)
        refund = Refund.objects.get(order=self.order)
        self.assertEqual(refund.status, RefundStatus.SUCCEEDED)
        self.assertEqual(refund.amount, 2500)

        refund_email = OutboxEmail.objects.get(namespace="billing", purpose="refund_receipt", metadata__refund_id=refund.refund_id)
        invoice_url = refund_email.context.get("invoice_url", "")
        self.assertIn(f"/billing/invoices/{self.order.id}/", invoice_url)
