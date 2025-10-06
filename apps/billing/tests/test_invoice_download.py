from __future__ import annotations

from unittest import mock

from django.test import TestCase, override_settings

from apps.billing.models import InvoiceArtifact, InvoiceKind, Order, OrderItem
from apps.billing.services.invoice import build_invoice_url, get_invoice_service
from apps.messaging.exceptions import TokenExpiredError


@override_settings(BILLING_ENABLED=True, INVOICING_ENABLED=True)
class InvoiceDownloadTests(TestCase):
    def setUp(self) -> None:
        self.order = Order.objects.create(
            email="download@example.com",
            currency="EUR",
            amount_subtotal=1500,
            tax_amount=0,
            amount_total=1500,
            list_price_cents=1500,
            metadata={"source": "test"},
        )
        OrderItem.objects.create(
            order=self.order,
            product_sku="sku-download",
            quantity=1,
            unit_amount=1500,
            description="Download test",
        )
        self.service = get_invoice_service()
        self.service.generate(self.order)

    def test_download_success(self) -> None:
        url = build_invoice_url(self.order)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertGreater(int(response.get("Content-Length", "0")), 0)

    def test_download_invalid_token(self) -> None:
        url = build_invoice_url(self.order) + "corrupted"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Invalid token", response.content)

    def test_download_email_mismatch(self) -> None:
        with mock.patch("apps.messaging.tokens.TokenService.read_signed") as read_signed:
            payload_mock = mock.Mock()
            payload_mock.claims = {"order_id": self.order.id, "email": "hacker@example.com"}
            read_signed.return_value = payload_mock
            url = build_invoice_url(self.order)
            response = self.client.get(url)
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Token mismatch", response.content)

    def test_download_expired_token(self) -> None:
        with mock.patch(
            "apps.billing.views.invoice.TokenService.read_signed",
            side_effect=TokenExpiredError("expired"),
        ):
            url = build_invoice_url(self.order)
            response = self.client.get(url)
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Token expired", response.content)

    def test_lazy_generation_when_artifact_missing(self) -> None:
        artifact = InvoiceArtifact.objects.get(order=self.order, kind=InvoiceKind.INVOICE)
        storage_path = artifact.storage_path
        artifact.delete()
        self.service.storage.delete(storage_path)

        url = build_invoice_url(self.order)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        regenerated = InvoiceArtifact.objects.get(order=self.order, kind=InvoiceKind.INVOICE)
        self.assertEqual(regenerated.storage_path, storage_path)
        self.assertTrue(self.service.storage.exists(storage_path))
