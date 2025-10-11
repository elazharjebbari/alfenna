from __future__ import annotations

import uuid
from typing import Any, Mapping

from django.conf import settings
from django.db import transaction

from apps.billing.models import Order

from .entitlement import EntitlementService
from .invoice import InvoiceService, get_invoice_service, issue_invoice
from .order import CheckoutResult, ItemSpec, OrderService, get_order_service
from .pack import PackCheckoutService, PackLine, PackTotals, compute_pack_totals
from .pricing import PriceService
from .refund import RefundService, get_refund_service
from .stripe_client import StripeClient, get_client


def _resolve_default_course() -> Any | None:
    """Return the default course used when no explicit course is provided."""

    default_slug = getattr(settings, "DEFAULT_CHECKOUT_COURSE_SLUG", "bougies-naturelles")
    if not default_slug:
        return None

    from apps.catalog.models.models import Course  # late import to avoid cycles

    return (
        Course.objects.filter(slug=default_slug, is_published=True)
        .only("id", "slug")
        .first()
    )

__all__ = [
    "CheckoutResult",
    "EntitlementService",
    "PackCheckoutService",
    "PackLine",
    "PackTotals",
    "InvoiceService",
    "issue_invoice",
    "ItemSpec",
    "OrderService",
    "PaymentService",
    "PriceService",
    "compute_pack_totals",
    "RefundService",
    "StripeClient",
    "get_client",
    "get_invoice_service",
    "get_order_service",
    "get_refund_service",
]


class PaymentService:
    _orders: OrderService | None = None

    @classmethod
    def _order_service(cls) -> OrderService:
        if cls._orders is None:
            cls._orders = get_order_service()
        return cls._orders

    @staticmethod
    def _ensure_enabled() -> None:
        if not getattr(settings, "BILLING_ENABLED", False):
            raise RuntimeError("Billing module disabled by feature toggle")

    @classmethod
    def create_or_update_order_and_intent(
        cls,
        *,
        user: Any | None,
        email: str,
        currency: str,
        course: Any | None = None,
        price_plan: Any | None = None,
        plan_slug: str | None = None,
        existing_order: Order | None = None,
        coupon: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> tuple[Order, Mapping[str, Any]]:
        cls._ensure_enabled()

        from apps.catalog.models.models import Course  # late import to avoid cycles
        from apps.marketing.models.models_pricing import PricePlan  # late import to avoid cycles

        currency_code = PriceService.select_currency(currency)
        plan = price_plan
        if plan is None and plan_slug:
            plan = PricePlan.objects.filter(slug=plan_slug, is_active=True).first()
            if plan is None:
                raise ValueError(f"Unknown price plan slug={plan_slug}")
        if plan is None and existing_order:
            plan = existing_order.price_plan

        course_obj = course
        if course_obj is None and existing_order:
            course_obj = existing_order.course
        if course_obj is None:
            course_obj = _resolve_default_course()

        if plan:
            totals = PriceService.compute_total_from_plan(plan, currency_code, coupon=coupon)
        elif course_obj:
            amount_subtotal = PriceService.course_amount_cents(course_obj, currency_code)
            tax_amount = 0
            amount_total = amount_subtotal + tax_amount
            totals = {
                "currency": currency_code,
                "amount_subtotal": amount_subtotal,
                "tax_amount": tax_amount,
                "amount_total": amount_total,
                "list_price_cents": amount_subtotal,
                "discount_pct": 0,
                "coupon": coupon or "",
            }
        else:
            raise ValueError("Either price_plan or course must be provided to create an order")

        order_service = cls._order_service()

        customer_profile = order_service.ensure_customer_profile(
            email=email,
            user=user,
            guest_id=(metadata or {}).get("guest_id"),
        )

        idempotency_key = existing_order.idempotency_key if existing_order else f"order:{uuid.uuid4().hex}"
        items = [
            ItemSpec(
                sku=f"plan:{getattr(plan, 'slug', '')}" if plan else f"course:{getattr(course_obj, 'slug', '')}",
                quantity=1,
                unit_amount=totals["amount_total"],
                description=getattr(plan, "title", getattr(course_obj, "title", "")),
            )
        ]
        metadata_payload = {
            "list_price_cents": totals.get("list_price_cents", totals["amount_total"]),
            "discount_pct": str(totals.get("discount_pct", 0)),
            "promo_code": totals.get("coupon", ""),
        }
        if metadata:
            metadata_payload.update(metadata)

        with transaction.atomic():
            order = order_service.prepare_order(
                user=user,
                email=email,
                currency=currency_code,
                amount_subtotal=totals["amount_subtotal"],
                tax_amount=totals.get("tax_amount", 0),
                amount_total=totals["amount_total"],
                price_plan=plan,
                course=course_obj,
                idempotency_key=idempotency_key,
                metadata=metadata_payload,
                customer_profile=customer_profile,
                items=items,
            )

        payment_intent = order_service.ensure_payment_intent(
            order,
            idempotency_key=order.idempotency_key,
            metadata=metadata_payload,
        )

        publishable_key = getattr(settings, "STRIPE_PUBLISHABLE_KEY", "")
        response = {
            "client_secret": payment_intent.get("client_secret", f"cs_test_{order.id}"),
            "publishable_key": publishable_key,
            "payment_intent": payment_intent,
        }
        return order, response


# Backwards compatibility for modules importing legacy module attribute.
PriceService = PriceService
EntitlementService = EntitlementService
RefundService = RefundService
StripeClient = StripeClient
InvoiceService = InvoiceService
PackCheckoutService = PackCheckoutService
PackLine = PackLine
PackTotals = PackTotals
compute_pack_totals = compute_pack_totals
