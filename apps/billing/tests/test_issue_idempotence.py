from __future__ import annotations

from django.test import TestCase, override_settings

from apps.billing.models import InvoiceArtifact, InvoiceKind, Order, OrderItem
from apps.billing.services.invoice import issue_invoice


@override_settings(BILLING_ENABLED=True, INVOICING_ENABLED=True)
class InvoiceIssueIdempotenceTests(TestCase):
    def setUp(self) -> None:
        self.order = Order.objects.create(
            email="idempotence@example.com",
            currency="EUR",
            amount_subtotal=2500,
            tax_amount=0,
            amount_total=2500,
            list_price_cents=2500,
            metadata={"source": "test"},
        )
        OrderItem.objects.create(
            order=self.order,
            product_sku="sku-idempotence",
            quantity=1,
            unit_amount=2500,
        )

    def test_issue_invoice_is_idempotent(self) -> None:
        issue_invoice(self.order)
        issue_invoice(self.order)
        artifacts = InvoiceArtifact.objects.filter(order=self.order, kind=InvoiceKind.INVOICE)
        self.assertEqual(artifacts.count(), 1)
