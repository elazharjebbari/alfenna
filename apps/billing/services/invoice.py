from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import Storage, default_storage
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from urllib.parse import urlencode

from apps.billing.metrics import record_invoice_issue
from apps.billing.models import InvoiceArtifact, InvoiceKind, Order
from apps.messaging.tokens import TokenService
from apps.messaging.utils import secure_base_url

DEFAULT_TEMPLATE = "billing/invoice.html"


@dataclass
class InvoiceRenderResult:
    invoice: InvoiceArtifact
    receipt: InvoiceArtifact
    html: str
    pdf_path: str


class InvoiceService:
    def __init__(self, *, storage: Storage | None = None, template_name: str = DEFAULT_TEMPLATE) -> None:
        self.storage = storage or default_storage
        self.template_name = template_name

    def generate(self, order: Order, *, context: Mapping[str, Any] | None = None) -> InvoiceRenderResult:
        ctx = self._build_context(order, context or {})
        html = render_to_string(self.template_name, ctx)
        html_bytes = html.encode("utf-8")
        html_checksum = self._checksum(html_bytes)

        out_dir = self._artifact_dir(order)
        html_name = f"{order.reference}-invoice.html"
        html_path = self._store_file(out_dir / html_name, html_bytes)

        pdf_bytes = self._render_pdf(ctx)
        pdf_checksum = self._checksum(pdf_bytes)
        pdf_name = f"{order.reference}-invoice.pdf"
        pdf_path = self._store_file(out_dir / pdf_name, pdf_bytes)

        invoice, _ = InvoiceArtifact.objects.update_or_create(
            order=order,
            kind=InvoiceKind.INVOICE,
            defaults={
                "storage_path": pdf_path,
                "checksum": pdf_checksum,
                "rendered_at": timezone.now(),
            },
        )
        receipt, _ = InvoiceArtifact.objects.update_or_create(
            order=order,
            kind=InvoiceKind.RECEIPT,
            defaults={
                "storage_path": html_path,
                "checksum": html_checksum,
                "rendered_at": timezone.now(),
            },
        )
        return InvoiceRenderResult(invoice=invoice, receipt=receipt, html=html, pdf_path=pdf_path)

    def ensure_invoice_pdf(self, order: Order) -> InvoiceArtifact:
        """Return the invoice artifact, regenerating it if missing or stale."""

        artifact = InvoiceArtifact.objects.filter(order=order, kind=InvoiceKind.INVOICE).first()
        if artifact and self._storage_exists(artifact.storage_path):
            return artifact

        result = self.generate(order)
        return result.invoice

    # ------------------------------------------------------------------
    def _build_context(self, order: Order, extra: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "order": order,
            "items": list(order.items.all()),
            "now": timezone.now(),
            **extra,
        }

    def _artifact_dir(self, order: Order) -> Path:
        base = Path(getattr(settings, "BILLING_INVOICE_ROOT", "billing/invoices"))
        return base / str(order.id)

    def _store_file(self, path: Path, data: bytes) -> str:
        path_str = str(path).replace(os.sep, "/")
        if self.storage.exists(path_str):
            self.storage.delete(path_str)
        self.storage.save(path_str, ContentFile(data))
        return path_str

    def _storage_exists(self, path: str) -> bool:
        try:
            return self.storage.exists(path)
        except Exception:  # pragma: no cover - storage backend failure
            return False

    def _render_pdf(self, ctx: Mapping[str, Any]) -> bytes:
        lines = [
            "Invoice",
            f"Order ID: {ctx['order'].id}",
            f"Reference: {ctx['order'].reference}",
            f"Total: {ctx['order'].amount_total / 100:.2f} {ctx['order'].currency}",
            "Items:",
        ]
        for item in ctx["items"]:
            lines.append(
                f" - {getattr(item, 'description', '') or item.product_sku}: {item.quantity} x {item.unit_amount / 100:.2f}"
            )
        payload = "\n".join(lines)
        escaped = self._escape_pdf_text(payload)
        text_stream = f"BT /F1 12 Tf 50 750 Td ({escaped}) Tj ET"
        stream_bytes = text_stream.encode("utf-8")

        objects = [
            "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
            "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
            "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj",
            f"4 0 obj << /Length {len(stream_bytes)} >> stream\n{text_stream}\nendstream endobj",
            "5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj",
        ]

        pdf = "%PDF-1.4\n"
        offsets: list[int] = [0]
        for obj in objects:
            offsets.append(len(pdf))
            pdf += obj + "\n"
        xref_offset = len(pdf)
        pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
        for off in offsets[1:]:
            pdf += f"{off:010} 00000 n \n"
        pdf += f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\n"
        pdf += f"startxref\n{xref_offset}\n%%EOF"
        return pdf.encode("utf-8")

    @staticmethod
    def _checksum(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _escape_pdf_text(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def get_invoice_service() -> InvoiceService:
    return InvoiceService()


def issue_invoice(
    order: Order,
    *,
    context: Mapping[str, Any] | None = None,
) -> InvoiceArtifact:
    """Ensure the invoice exists and enqueue notification delivery."""

    service = get_invoice_service()
    artifact_exists = InvoiceArtifact.objects.filter(order=order, kind=InvoiceKind.INVOICE).exists()
    try:
        if context:
            artifact = service.generate(order, context=context).invoice
        else:
            artifact = service.ensure_invoice_pdf(order)
    except Exception:
        record_invoice_issue("error")
        raise
    else:
        record_invoice_issue("idempotent" if artifact_exists else "success")

    def _enqueue() -> None:
        try:
            from apps.billing.tasks import send_invoice_email  # inline import to avoid cycles

            send_invoice_email.delay(order.id)
        except Exception:  # pragma: no cover - defensive
            logging.getLogger("billing.invoice").exception(
                "invoice_email_enqueue_failed",
                extra={"order_id": order.id},
            )

    transaction.on_commit(_enqueue)
    return artifact


def build_invoice_url(order: Order) -> str:
    """Construct a signed download URL for the given order."""

    token = TokenService.sign(
        namespace=getattr(settings, "BILLING_INVOICE_TOKEN_NAMESPACE", "billing"),
        purpose=getattr(settings, "BILLING_INVOICE_TOKEN_PURPOSE", "invoice_download"),
        claims={
            "order_id": order.id,
            "email": (order.email or "").lower(),
        },
        ttl_seconds=getattr(settings, "BILLING_INVOICE_TOKEN_TTL", 60 * 60 * 24 * 14),
    )
    base_url = secure_base_url()
    query = urlencode({"t": token})
    return f"{base_url}/billing/invoices/{order.id}/?{query}"
