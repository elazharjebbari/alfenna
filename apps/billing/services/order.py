from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.billing.domain import state as order_state
from apps.billing.domain.errors import InvalidTransition
from apps.billing.models import (
    CustomerProfile,
    Order,
    OrderItem,
    OrderStatus,
    PaymentAttempt,
)
from apps.billing.services.stripe_client import StripeClient, get_client

logger = logging.getLogger("billing.order_service")


@dataclass(frozen=True)
class ItemSpec:
    sku: str
    quantity: int
    unit_amount: int
    description: str = ""
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class CheckoutResult:
    order: Order
    payment_intent: Mapping[str, Any]
    publishable_key: str

    @property
    def client_secret(self) -> str:
        return str(self.payment_intent.get("client_secret", ""))


class OrderService:
    def __init__(self, *, stripe_client: StripeClient | None = None) -> None:
        self.client = stripe_client or get_client()

    # ------------------------------------------------------------------
    def ensure_customer_profile(
        self,
        *,
        email: str,
        user: Any | None,
        stripe_customer_id: str | None = None,
        guest_id: str | None = None,
    ) -> CustomerProfile:
        profile = None
        if stripe_customer_id:
            profile = CustomerProfile.objects.filter(stripe_customer_id=stripe_customer_id).first()
        if profile is None and user is not None:
            profile = CustomerProfile.objects.filter(user=user).first()
        if profile is None:
            profile = CustomerProfile.objects.create(
                user=user,
                email=email,
                stripe_customer_id=stripe_customer_id or "",
                guest_id=guest_id or "",
            )
        else:
            updates: dict[str, Any] = {}
            if user and not profile.user_id:
                updates["user"] = user
            if stripe_customer_id and not profile.stripe_customer_id:
                updates["stripe_customer_id"] = stripe_customer_id
            if guest_id and profile.guest_id != guest_id:
                updates["guest_id"] = guest_id
            if email and profile.email != email:
                updates["email"] = email
            if updates:
                CustomerProfile.objects.filter(pk=profile.pk).update(**updates)
                profile.refresh_from_db()
        if guest_id and guest_id != profile.merged_from_guest_id and user and profile.user_id == getattr(user, "id", profile.user_id):
            profile.mark_guest_merge(guest_id)
        return profile

    @transaction.atomic
    def prepare_order(
        self,
        *,
        user: Any | None,
        email: str,
        currency: str,
        amount_subtotal: int,
        tax_amount: int,
        amount_total: int,
        price_plan: Any | None,
        course: Any | None,
        idempotency_key: str,
        metadata: Mapping[str, Any] | None,
        customer_profile: CustomerProfile | None,
        items: Sequence[ItemSpec],
    ) -> Order:
        order = (
            Order.objects.select_for_update()
            .filter(idempotency_key=idempotency_key)
            .first()
        )
        metadata_dict = dict(metadata or {})
        if order is None:
            order = Order.objects.create(
                user=user,
                email=email,
                currency=currency,
                amount_subtotal=amount_subtotal,
                tax_amount=tax_amount,
                amount_total=amount_total,
                price_plan=price_plan,
                course=course,
                pricing_code=getattr(price_plan, "slug", ""),
                list_price_cents=metadata_dict.get("list_price_cents", amount_total),
                discount_pct_effective=metadata_dict.get("discount_pct", 0),
                promo_code=metadata_dict.get("promo_code", ""),
                status=OrderStatus.DRAFT,
                idempotency_key=idempotency_key,
                metadata=metadata_dict,
                customer_profile=customer_profile,
            )
        else:
            order.user = user or order.user
            order.email = email
            order.currency = currency
            order.amount_subtotal = amount_subtotal
            order.tax_amount = tax_amount
            order.amount_total = amount_total
            order.price_plan = price_plan
            order.course = course
            order.pricing_code = getattr(price_plan, "slug", order.pricing_code)
            order.metadata = metadata_dict
            if customer_profile and order.customer_profile_id != customer_profile.id:
                order.customer_profile = customer_profile
            order.list_price_cents = metadata_dict.get("list_price_cents", order.list_price_cents)
            if "discount_pct" in metadata_dict:
                order.discount_pct_effective = metadata_dict["discount_pct"]
            if "promo_code" in metadata_dict:
                order.promo_code = metadata_dict["promo_code"]
            order.save(
                update_fields=[
                    "user",
                    "email",
                    "currency",
                    "amount_subtotal",
                    "tax_amount",
                    "amount_total",
                    "price_plan",
                    "course",
                    "pricing_code",
                    "metadata",
                    "customer_profile",
                    "list_price_cents",
                    "discount_pct_effective",
                    "promo_code",
                    "updated_at",
                ]
            )
        self._sync_items(order, items)
        self._apply_transition(order, order_state.OrderEvent.CHECKOUT_CREATED)
        return order

    def _sync_items(self, order: Order, items: Sequence[ItemSpec]) -> None:
        OrderItem.objects.filter(order=order).delete()
        for item in items:
            OrderItem.objects.create(
                order=order,
                product_sku=item.sku,
                quantity=item.quantity,
                unit_amount=item.unit_amount,
                description=item.description,
                metadata=dict(item.metadata or {}),
            )

    def ensure_payment_intent(
        self,
        order: Order,
        *,
        idempotency_key: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        attempt_key = f"pi:{idempotency_key}"
        attempt = PaymentAttempt.objects.filter(idempotency_key=attempt_key).first()
        metadata_dict = {"order_id": str(order.id)}
        metadata_dict.update(metadata or {})

        if attempt and attempt.intent_id:
            logger.debug("billing.payment.intent.cache", extra={"order_id": order.id, "intent_id": attempt.intent_id})
            return attempt.raw_payload

        payload = self.client.create_payment_intent(
            amount=order.amount_total,
            currency=order.currency,
            idempotency_key=attempt_key,
            metadata=metadata_dict,
            customer=order.customer_profile.stripe_customer_id if order.customer_profile else None,
            automatic_payment_methods={"enabled": True},
        )
        PaymentAttempt.objects.update_or_create(
            order=order,
            idempotency_key=attempt_key,
            defaults={
                "intent_id": payload.get("id", ""),
                "status": payload.get("status", "created"),
                "raw_payload": payload,
            },
        )
        stripe_customer_id = payload.get("customer") or order.stripe_customer_id or ""
        updates = {
            "stripe_payment_intent_id": payload.get("id", order.stripe_payment_intent_id),
            "stripe_customer_id": stripe_customer_id,
            "updated_at": timezone.now(),
        }
        Order.objects.filter(pk=order.pk).update(**updates)
        order.stripe_payment_intent_id = updates["stripe_payment_intent_id"]
        order.stripe_customer_id = stripe_customer_id

        if payload.get("status") == "requires_action":
            self._apply_transition(
                order,
                order_state.OrderEvent.PAYMENT_REQUIRES_ACTION,
                context={"stripe_payment_intent": payload.get("id"), "source": "payment_intent"},
            )

        return payload

    @transaction.atomic
    def mark_payment_succeeded(
        self,
        order: Order,
        payload: Mapping[str, Any],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Order:
        locked_order = Order.objects.select_for_update().get(pk=order.pk)
        self._apply_transition(locked_order, order_state.OrderEvent.PAYMENT_SUCCEEDED, context=context)
        Order.objects.filter(pk=locked_order.pk).update(updated_at=timezone.now())
        PaymentAttempt.objects.filter(order=locked_order, intent_id=locked_order.stripe_payment_intent_id).update(
            status="succeeded",
            raw_payload=dict(payload),
        )
        order.refresh_from_db()
        return order

    @transaction.atomic
    def mark_refund_requested(
        self,
        order: Order,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Order:
        locked_order = Order.objects.select_for_update().get(pk=order.pk)
        self._apply_transition(locked_order, order_state.OrderEvent.REFUND_REQUESTED, context=context)
        Order.objects.filter(pk=locked_order.pk).update(updated_at=timezone.now())
        order.refresh_from_db()
        return order

    @transaction.atomic
    def mark_refund_succeeded(
        self,
        order: Order,
        payload: Mapping[str, Any],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Order:
        locked_order = Order.objects.select_for_update().get(pk=order.pk)
        self._apply_transition(locked_order, order_state.OrderEvent.REFUND_SUCCEEDED, context=context)
        Order.objects.filter(pk=locked_order.pk).update(updated_at=timezone.now())
        PaymentAttempt.objects.filter(order=locked_order, intent_id=locked_order.stripe_payment_intent_id).update(
            status="refunded",
            raw_payload=dict(payload),
        )
        order.refresh_from_db()
        return order

    @transaction.atomic
    def mark_payment_failed(
        self,
        order: Order,
        payload: Mapping[str, Any],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> Order:
        locked_order = Order.objects.select_for_update().get(pk=order.pk)
        self._apply_transition(locked_order, order_state.OrderEvent.PAYMENT_FAILED, context=context)
        Order.objects.filter(pk=locked_order.pk).update(updated_at=timezone.now())
        PaymentAttempt.objects.filter(order=locked_order, intent_id=locked_order.stripe_payment_intent_id).update(
            status="failed",
            raw_payload=dict(payload),
        )
        order.refresh_from_db()
        return order

    def _apply_transition(
        self,
        order: Order,
        event: order_state.OrderEvent,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        if not order_state.is_allowed(order.status, event):
            return
        try:
            next_state = order_state.transition(order.status, event)
        except InvalidTransition:
            logger.warning(
                "billing.transition.invalid",
                extra={"order_id": order.id, "status": order.status, "event": event.value},
            )
            return
        if next_state != order.status:
            previous_state = order.status
            Order.objects.filter(pk=order.pk).update(
                status=next_state,
                version=F("version") + 1,
                updated_at=timezone.now(),
            )
            order.status = next_state
            order.version += 1
            extra = {
                "order_id": order.id,
                "event": event.value,
                "from": previous_state,
                "to": next_state,
            }
            if context:
                extra.update({k: v for k, v in context.items() if isinstance(k, str)})
            logger.info("billing.order.transition", extra=extra)


def get_order_service() -> OrderService:
    return OrderService()
