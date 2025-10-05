import os
import tempfile

from django.test import TestCase, override_settings

from apps.billing.models import InvoiceArtifact, Order, OrderItem, OrderStatus
from apps.billing.services.invoice import InvoiceService


class InvoiceGenerationTests(TestCase):
    def setUp(self) -> None:
        self.order = Order.objects.create(
            email="buyer@example.com",
            currency="EUR",
            amount_subtotal=1000,
            tax_amount=0,
            amount_total=1000,
            status=OrderStatus.PAID,
        )
        OrderItem.objects.create(
            order=self.order,
            product_sku="course:test",
            quantity=1,
            unit_amount=1000,
            description="Formation test",
        )

    def test_generate_invoice_creates_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root, BILLING_INVOICE_ROOT="billing/tests"):
                service = InvoiceService()
                result = service.generate(self.order)

                invoice_path = os.path.join(media_root, result.invoice.storage_path)
                receipt_path = os.path.join(media_root, result.receipt.storage_path)

                self.assertTrue(result.invoice.checksum)
                self.assertTrue(result.receipt.checksum)
                self.assertTrue(os.path.exists(invoice_path))
                self.assertTrue(os.path.exists(receipt_path))

        self.assertTrue(InvoiceArtifact.objects.filter(order=self.order, kind=result.invoice.kind).exists())
