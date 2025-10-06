from __future__ import annotations

from django.test import TestCase, override_settings

from apps.billing.models import InvoiceArtifact, InvoiceKind, Order, OrderItem, OrderStatus
from apps.billing.webhooks import _process_event
from apps.messaging.models import OutboxEmail


@override_settings(BILLING_ENABLED=True, INVOICING_ENABLED=True, STRIPE_WEBHOOK_SECRET="whsec_test")
class WebhookSuccessFlowTests(TestCase):
    def setUp(self) -> None:
        self.order = Order.objects.create(
            email="webhook@example.com",
            currency="EUR",
            amount_subtotal=8900,
            tax_amount=0,
            amount_total=8900,
            list_price_cents=8900,
            metadata={"order_id": ""},
        )
        self.order.metadata["order_id"] = str(self.order.id)
        self.order.save(update_fields=["metadata"])
        self.order.stripe_payment_intent_id = f"pi_{self.order.id}"
        self.order.save(update_fields=["stripe_payment_intent_id"])
        OrderItem.objects.create(
            order=self.order,
            product_sku="sku-webhook",
            quantity=1,
            unit_amount=8900,
        )

    def test_payment_intent_success_creates_invoice_and_email(self) -> None:
        event = {
            "id": "evt_success",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": self.order.stripe_payment_intent_id,
                    "metadata": {"order_id": str(self.order.id)},
                    "amount_received": self.order.amount_total,
                    "currency": self.order.currency.lower(),
                    "payment_method": "pm_test",
                    "latest_charge": "ch_test",
                    "status": "succeeded",
                }
            },
        }
        _process_event(event, correlation_id="corr-success", stripe_signature="sig")

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.PAID)
        artifact = InvoiceArtifact.objects.get(order=self.order, kind=InvoiceKind.INVOICE)
        self.assertTrue(artifact.storage_path.endswith(".pdf"))

        outbox = OutboxEmail.objects.get(namespace="billing", purpose="invoice_ready", metadata__order_id=self.order.id)
        invoice_url = outbox.context.get("invoice_url", "")
        self.assertIn(f"/billing/invoices/{self.order.id}/", invoice_url)
