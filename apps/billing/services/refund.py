from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping

from django.db import transaction

from apps.billing.models import Order, OrderStatus, Refund, RefundStatus
from apps.billing.services.order import OrderService, get_order_service
from apps.billing.services.stripe_client import StripeClient, get_client


log = logging.getLogger("billing.refund_service")


@dataclass
class RefundResult:
    refund: Refund
    payload: Mapping[str, Any]


class RefundService:
    def __init__(self, *, stripe_client: StripeClient | None = None, order_service: OrderService | None = None) -> None:
        self.client = stripe_client or get_client()
        self.orders = order_service or get_order_service()

    @transaction.atomic
    def initiate(self, order: Order, *, amount: int | None = None, reason: str | None = None) -> RefundResult:
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.status not in (OrderStatus.PAID, OrderStatus.REFUNDED):
            raise ValueError("Refunds only supported for paid/refunded orders")
        order = self.orders.mark_refund_requested(order, context={"source": "refund_service"})
        payload = self.client.create_refund(
            intent_id=order.stripe_payment_intent_id or None,
            amount=amount or order.amount_total,
            idempotency_key=f"refund:{order.id}:{amount or order.amount_total}",
            reason=reason,
        )
        refund, _ = Refund.objects.update_or_create(
            order=order,
            refund_id=payload.get("id", f"rf_{order.id}"),
            defaults={
                "amount": payload.get("amount", amount or order.amount_total),
                "status": RefundStatus.REQUESTED,
                "raw_payload": payload,
            },
        )
        return RefundResult(refund=refund, payload=payload)

    @transaction.atomic
    def mark_succeeded(
        self,
        order: Order,
        payload: Mapping[str, Any],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Refund:
        order = Order.objects.select_for_update().get(pk=order.pk)
        refund_id = str(payload.get("id") or payload.get("refund") or "")
        refund, _ = Refund.objects.update_or_create(
            order=order,
            refund_id=refund_id or f"rf_{order.id}",
            defaults={
                "amount": int(payload.get("amount") or order.amount_total),
                "status": RefundStatus.SUCCEEDED,
                "raw_payload": payload,
            },
        )
        extra_context = dict(context or {})
        extra_context.setdefault("source", "webhook")
        self.orders.mark_refund_succeeded(order, payload, context=extra_context)
        transaction.on_commit(
            lambda: _enqueue_refund_email(refund.id)
        )
        return refund


def get_refund_service() -> RefundService:
    return RefundService()


def _enqueue_refund_email(refund_pk: int) -> None:
    try:
        from apps.billing.tasks import send_refund_email  # inline import to avoid cycles

        send_refund_email.delay(refund_pk)
    except Exception:  # pragma: no cover - defensive
        log.exception("refund_email_enqueue_failed", extra={"refund_id": refund_pk})
