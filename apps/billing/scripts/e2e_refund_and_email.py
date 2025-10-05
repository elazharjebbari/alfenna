"""Simulate a refund flow and verify refund email/link behaviour."""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.test import Client

from apps.billing.models import InvoiceKind, Order, OrderItem, OrderStatus
from apps.billing.services.entitlement import EntitlementService
from apps.billing.services.refund import RefundService
from apps.common.runscript_harness import binary_harness, skip
from apps.messaging.models import OutboxEmail


def _prepare_paid_order() -> Order:
    order = Order.objects.create(
        email="cli-refund@example.com",
        currency="EUR",
        amount_subtotal=5000,
        tax_amount=0,
        amount_total=5000,
        list_price_cents=5000,
        metadata={"source": "script"},
    )
    OrderItem.objects.create(
        order=order,
        product_sku="script-refund",
        quantity=1,
        unit_amount=5000,
        description="Script refund course",
    )
    order.stripe_payment_intent_id = f"pi_rf_{order.id}"
    order.save(update_fields=["stripe_payment_intent_id"])

    payload = {
        "id": "evt_cli_refund_paid",
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": order.stripe_payment_intent_id,
                "amount_received": order.amount_total,
                "currency": order.currency.lower(),
                "status": "succeeded",
            }
        },
    }
    EntitlementService.grant_entitlement(order, "payment_intent.succeeded", payload, context={"source": "script"})
    order.refresh_from_db()
    return order


@binary_harness
def run(*_args, **_kwargs):
    if not getattr(settings, "BILLING_ENABLED", False):
        return skip("BILLING_ENABLED toggle is disabled")
    if not getattr(settings, "INVOICING_ENABLED", False):
        return skip("INVOICING_ENABLED toggle is disabled")

    order = _prepare_paid_order()
    logs: list[str] = [f"order:{order.id} status:{order.status}"]
    if order.status != OrderStatus.PAID:
        logs.append("order not paid after setup")
        return {"ok": False, "name": "billing_e2e_refund", "duration": 0.0, "logs": logs}

    refund_payload = {
        "id": f"re_{order.id}",
        "amount": order.amount_total,
        "currency": order.currency.lower(),
        "payment_intent": order.stripe_payment_intent_id,
        "status": "succeeded",
    }
    RefundService().mark_succeeded(order, refund_payload, context={"source": "script"})
    order.refresh_from_db()
    logs.append(f"post_refund_status:{order.status}")

    if order.status not in {OrderStatus.REFUNDED, OrderStatus.PAID}:
        logs.append("order not updated after refund")
        return {"ok": False, "name": "billing_e2e_refund", "duration": 0.0, "logs": logs}

    artifact = order.artifacts.filter(kind=InvoiceKind.INVOICE).first()
    if artifact is None:
        logs.append("invoice artifact missing after refund")
        return {"ok": False, "name": "billing_e2e_refund", "duration": 0.0, "logs": logs}

    refund_email = (
        OutboxEmail.objects.filter(namespace="billing", purpose="refund_receipt", metadata__order_id=order.id)
        .order_by("-created_at")
        .first()
    )
    if refund_email is None:
        logs.append("refund email missing in outbox")
        return {"ok": False, "name": "billing_e2e_refund", "duration": 0.0, "logs": logs}

    invoice_url = refund_email.context.get("invoice_url")
    if not invoice_url:
        logs.append("invoice URL missing in refund email context")
        return {"ok": False, "name": "billing_e2e_refund", "duration": 0.0, "logs": logs}
    logs.append(f"invoice_url:{invoice_url}")

    response = Client().get(invoice_url)
    logs.append(f"GET {invoice_url} -> {response.status_code}")
    if response.status_code != 200 or response["Content-Type"] != "application/pdf":
        logs.append("invoice download failed after refund")
        return {"ok": False, "name": "billing_e2e_refund", "duration": 0.0, "logs": logs}

    refund_amount = Decimal(order.amount_total) / Decimal("100")
    logs.append(f"refund_amount:{refund_amount:.2f} {order.currency}")
    return {"ok": True, "name": "billing_e2e_refund", "duration": 0.0, "logs": logs}
