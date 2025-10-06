from __future__ import annotations

import logging
from decimal import Decimal

from celery import shared_task
from django.conf import settings

from apps.billing.metrics import record_invoice_email
from apps.billing.models import InvoiceArtifact, InvoiceKind, Order, Refund
from apps.billing.services import get_invoice_service, get_refund_service
from apps.billing.services.invoice import build_invoice_url


@shared_task(bind=True, ignore_result=False, max_retries=3, default_retry_delay=10)
def generate_invoice(self, order_id: int) -> str:
    order = Order.objects.get(pk=order_id)
    service = get_invoice_service()
    result = service.generate(order)
    return result.invoice.storage_path


@shared_task(bind=True, ignore_result=False, max_retries=3, default_retry_delay=10)
def initiate_refund(self, order_id: int, amount: int | None = None) -> str:
    order = Order.objects.get(pk=order_id)
    service = get_refund_service()
    result = service.initiate(order, amount=amount)
    return result.refund.refund_id


def _primary_recipient(order: Order) -> str:
    if order.email:
        return order.email
    user = getattr(order, "user", None)
    if user and getattr(user, "email", None):
        return user.email  # type: ignore[return-value]
    return ""


def _customer_name(order: Order) -> str:
    user = getattr(order, "user", None)
    if user and getattr(user, "first_name", ""):
        return user.first_name
    recipient = _primary_recipient(order)
    return recipient.split("@", 1)[0] if recipient else ""


def _site_name() -> str:
    seo_defaults = getattr(settings, "SEO_DEFAULTS", {}) or {}
    default_name = seo_defaults.get("site_name", "Lumière Academy")
    return getattr(settings, "SITE_NAME", default_name)


@shared_task(bind=True, ignore_result=False, max_retries=3, default_retry_delay=10)
def send_invoice_email(self, order_id: int) -> str | None:
    order = Order.objects.select_related("user").get(pk=order_id)
    recipient = _primary_recipient(order)
    if not recipient:
        record_invoice_email("skip_no_email")
        return None

    service = get_invoice_service()
    artifact = (
        InvoiceArtifact.objects.filter(order=order, kind=InvoiceKind.INVOICE).first()
        or service.ensure_invoice_pdf(order)
    )

    try:
        invoice_url = build_invoice_url(order)
        from apps.messaging.integrations import enqueue_invoice_ready  # inline import to avoid circular deps
        from apps.messaging.exceptions import TemplateNotFoundError  # type: ignore

        enqueue_invoice_ready(order, invoice_url=invoice_url, artifact_signature=artifact.checksum)
    except TemplateNotFoundError:  # pragma: no cover - optional template
        record_invoice_email("skip_no_template")
        logging.getLogger("billing.invoice").warning(
            "invoice_email_template_missing",
            extra={"order_id": order.id},
        )
        return None
    except Exception as exc:  # pragma: no cover - defensive
        record_invoice_email("error")
        raise exc
    else:
        record_invoice_email("success")
    return invoice_url


@shared_task(bind=True, ignore_result=False, max_retries=3, default_retry_delay=10)
def send_refund_email(self, refund_id: int) -> str | None:
    refund = Refund.objects.select_related("order", "order__user").get(pk=refund_id)
    order = refund.order
    recipient = _primary_recipient(order)
    if not recipient:
        record_invoice_email("skip_no_email")
        return None

    invoice_url = build_invoice_url(order)
    currency = (order.currency or "EUR").upper()
    refund_amount = Decimal(refund.amount or 0) / Decimal("100")
    original_amount = Decimal(order.amount_total or 0) / Decimal("100")
    is_full = refund.amount >= order.amount_total

    context = {
        "customer_name": _customer_name(order),
        "order_reference": order.reference or str(order.id),
        "refund_amount": f"{refund_amount:.2f}",
        "original_amount": f"{original_amount:.2f}",
        "currency": currency,
        "invoice_url": invoice_url,
        "is_full_refund": is_full,
        "site_name": _site_name(),
    }

    try:
        from apps.messaging.services import EmailService  # inline import to avoid circular deps
        from apps.messaging.exceptions import TemplateNotFoundError  # type: ignore

        EmailService.compose_and_enqueue(
            namespace="billing",
            purpose="refund_receipt",
            template_slug="billing/refund_receipt",
            to=[recipient],
            dedup_key=f"refund:{order.id}:{refund.refund_id}:{refund.amount}",
            context=context,
            metadata={"order_id": order.id, "refund_id": refund.refund_id},
        )
    except TemplateNotFoundError:  # pragma: no cover - optional template
        record_invoice_email("skip_no_template")
        logging.getLogger("billing.invoice").warning(
            "refund_email_template_missing",
            extra={"order_id": order.id, "refund_id": refund.refund_id},
        )
        return None
    except Exception as exc:  # pragma: no cover - defensive
        record_invoice_email("error")
        raise exc
    else:
        record_invoice_email("success")
    return invoice_url
