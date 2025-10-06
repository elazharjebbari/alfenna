"""Simulate a successful purchase flow and invoice download end-to-end."""
from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.test import Client

from apps.billing.models import InvoiceKind, Order, OrderItem, OrderStatus
from apps.billing.services.entitlement import EntitlementService
from apps.common.runscript_harness import binary_harness, skip
from apps.messaging.models import OutboxEmail


def _make_order() -> Order:
    order = Order.objects.create(
        email="cli-invoice@example.com",
        currency="EUR",
        amount_subtotal=10000,
        tax_amount=0,
        amount_total=10000,
        list_price_cents=10000,
        metadata={"source": "script"},
    )
    OrderItem.objects.create(
        order=order,
        product_sku="script-course",
        quantity=1,
        unit_amount=10000,
        description="Script course access",
    )
    return order


@binary_harness
def run(*_args, **_kwargs):
    if not getattr(settings, "BILLING_ENABLED", False):
        return skip("BILLING_ENABLED toggle is disabled")
    if not getattr(settings, "INVOICING_ENABLED", False):
        return skip("INVOICING_ENABLED toggle is disabled")

    order = _make_order()
    order.stripe_payment_intent_id = f"pi_{order.id}"
    order.save(update_fields=["stripe_payment_intent_id"])

    payload = {
        "id": "evt_cli_invoice",
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

    logs: list[str] = [f"order:{order.id} status:{order.status}"]
    if order.status != OrderStatus.PAID:
        return {"ok": False, "name": "billing_e2e_purchase", "duration": 0.0, "logs": logs + ["order not paid"]}

    artifact = order.artifacts.filter(kind=InvoiceKind.INVOICE).first()
    if artifact is None:
        logs.append("invoice artifact missing")
        return {"ok": False, "name": "billing_e2e_purchase", "duration": 0.0, "logs": logs}
    logs.append(f"artifact:{artifact.id} path:{artifact.storage_path}")

    outbox = (
        OutboxEmail.objects.filter(namespace="billing", purpose="invoice_ready", metadata__order_id=order.id)
        .order_by("-created_at")
        .first()
    )
    if outbox is None:
        logs.append("invoice email missing in outbox")
        return {"ok": False, "name": "billing_e2e_purchase", "duration": 0.0, "logs": logs}

    invoice_url = outbox.context.get("invoice_url")
    if not invoice_url:
        logs.append("invoice URL missing in outbox context")
        return {"ok": False, "name": "billing_e2e_purchase", "duration": 0.0, "logs": logs}
    logs.append(f"invoice_url:{invoice_url}")

    client = Client()
    response = client.get(invoice_url)
    logs.append(f"GET {invoice_url} -> {response.status_code}")
    if response.status_code != 200 or response["Content-Type"] != "application/pdf":
        logs.append("invoice download failed")
        return {"ok": False, "name": "billing_e2e_purchase", "duration": 0.0, "logs": logs}

    amount = Decimal(order.amount_total) / Decimal("100")
    logs.append(f"order_total:{amount:.2f} {order.currency}")
    return {"ok": True, "name": "billing_e2e_purchase", "duration": 0.0, "logs": logs}
