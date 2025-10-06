from __future__ import annotations

from django.test import TestCase, override_settings

from apps.billing.models import Order, OrderItem, Refund, RefundStatus
from apps.billing.services.invoice import get_invoice_service
from apps.billing.tasks import send_invoice_email, send_refund_email
from apps.messaging.models import OutboxEmail


@override_settings(BILLING_ENABLED=True, INVOICING_ENABLED=True)
class SendInvoiceEmailTaskTests(TestCase):
    def setUp(self) -> None:
        self.order = Order.objects.create(
            email="task@example.com",
            currency="EUR",
            amount_subtotal=4200,
            tax_amount=0,
            amount_total=4200,
            list_price_cents=4200,
            metadata={"source": "test"},
        )
        OrderItem.objects.create(
            order=self.order,
            product_sku="sku-task",
            quantity=1,
            unit_amount=4200,
        )
        self.artifact = get_invoice_service().generate(self.order).invoice

    def test_task_enqueues_email_once(self) -> None:
        send_invoice_email.apply(args=(self.order.id,))
        outbox = OutboxEmail.objects.get(namespace="billing", purpose="invoice_ready")
        self.assertIn(self.artifact.checksum, outbox.dedup_key)
        self.assertEqual(outbox.metadata.get("order_id"), self.order.id)
        self.assertEqual(outbox.metadata.get("invoice_signature"), self.artifact.checksum)
        self.assertIn("invoice_url", outbox.context)

    def test_task_skips_when_no_recipient(self) -> None:
        self.order.email = ""
        self.order.save(update_fields=["email"])
        OutboxEmail.objects.all().delete()

        result = send_invoice_email.apply(args=(self.order.id,))
        self.assertIsNone(result.result)
        self.assertEqual(OutboxEmail.objects.count(), 0)

    def test_refund_email_task_enqueues(self) -> None:
        refund = Refund.objects.create(
            order=self.order,
            refund_id="re_task",
            amount=4200,
            status=RefundStatus.SUCCEEDED,
        )
        send_refund_email.apply(args=(refund.id,))

        outbox = OutboxEmail.objects.get(namespace="billing", purpose="refund_receipt")
        self.assertEqual(outbox.metadata.get("refund_id"), refund.refund_id)
        self.assertIn("invoice_url", outbox.context)
