from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Tuple
from uuid import uuid4

from django.conf import settings
from django.utils.http import urlencode
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.leads.permissions import PublicPOSTOnly
from apps.catalog.models import Product

logger = logging.getLogger(__name__)


def _build_mock_redirect_url(request) -> str:
    params = {"sid": uuid4().hex, "paid": "1"}
    base_path = "/pay/sandbox/"
    if request is not None:
        return request.build_absolute_uri(f"{base_path}?{urlencode(params)}")
    return f"{base_path}?{urlencode(params)}"


def _create_stripe_session(payload: Dict[str, Any], request) -> str | None:
    secret_key = getattr(settings, "STRIPE_SECRET_KEY", "")
    if not secret_key:
        return None

    try:
        import stripe

        stripe.api_key = secret_key

        product_name = payload.get("product_name") or payload.get("product") or "Commande"
        amount_minor = payload.get("amount_minor")
        currency = (payload.get("currency") or "mad").upper()

        if amount_minor is None:
            amount_minor = 1000  # défaut: 10.00

        success_query = urlencode({"paid": 1})
        success_url = request.build_absolute_uri(f"/checkout/success/?{success_query}") if request else f"/checkout/success/?{success_query}"
        cancel_url = request.build_absolute_uri("/") if request else "/"

        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": currency.lower(),
                        "product_data": {"name": product_name},
                        "unit_amount": int(amount_minor),
                    },
                    "quantity": 1,
                }
            ],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={k: str(v) for k, v in payload.items() if k != "signed_token"},
        )
        return getattr(session, "url", None)
    except Exception:  # pragma: no cover - Stripe errors fallback to mock
        logger.exception("Stripe checkout session creation failed; falling back to sandbox redirect")
        return None


def _coerce_int(value: Any) -> int | None:
    if value in (None, "", False):
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def _price_to_minor(value: Any) -> int | None:
    if value in (None, "", False):
        return None
    try:
        cents = (Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return None
    return int(cents)


def _resolve_product(payload: Dict[str, Any]) -> Product | None:
    lookup_keys = ("product_id", "product", "product_slug", "slug")
    for key in lookup_keys:
        value = payload.get(key)
        if not value:
            continue
        try:
            product = Product.objects.filter(pk=int(str(value)), is_active=True).first()
            if product:
                return product
        except (ValueError, TypeError):
            product = Product.objects.filter(slug=str(value), is_active=True).first()
            if product:
                return product
    return None


def _compute_amount(payload: Dict[str, Any], product: Product | None) -> Tuple[int | None, str | None, int, int, int]:
    if not product:
        return None, None, 0, 0, 0

    quantity = _coerce_int(payload.get("quantity")) or 1
    if quantity <= 0:
        quantity = 1

    if product.promo_price and product.price and product.promo_price < product.price:
        unit_minor = _price_to_minor(product.promo_price)
    else:
        unit_minor = _price_to_minor(product.promo_price or product.price)
    if unit_minor is None:
        return None, product.currency

    subtotal_minor = unit_minor * quantity

    discount_minor = 0
    if str(payload.get("payment_method", "")).lower() == "online":
        extra = product.extra or {}
        discount_raw = None
        if isinstance(extra, dict):
            discount_raw = extra.get("online_discount_amount")
            if discount_raw in (None, ""):
                ui_texts = extra.get("ui_texts") if isinstance(extra.get("ui_texts"), dict) else {}
                discount_raw = ui_texts.get("online_discount_amount") if isinstance(ui_texts, dict) else None
        discount_minor = _price_to_minor(discount_raw)
        if discount_minor is None:
            discount_minor = 0
    discount_minor = max(0, min(discount_minor, subtotal_minor))

    bump_minor = _coerce_int(payload.get("checkout_bump_minor"))
    if bump_minor is None:
        bump_minor = _price_to_minor(payload.get("checkout_bump_amount")) or 0
    bump_minor = max(bump_minor or 0, 0)

    total_minor = max(subtotal_minor - discount_minor + bump_minor, 0)
    return total_minor, product.currency, discount_minor, subtotal_minor, bump_minor


class CheckoutSessionView(APIView):
    """Create a checkout session for online payments."""

    permission_classes = [PublicPOSTOnly]
    authentication_classes: list[Any] = []

    def post(self, request, *args, **kwargs):
        if isinstance(request.data, dict):
            payload = dict(request.data)
        else:
            payload = {}
        payment_method = str(payload.get("payment_method", "")).lower()

        if payment_method != "online":
            return Response(
                {"detail": _("payment_method must be 'online'.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        product = _resolve_product(payload)
        explicit_minor = (
            _coerce_int(payload.get("checkout_total_minor"))
            or _coerce_int(payload.get("amount_cents"))
            or _coerce_int(payload.get("amount_minor"))
        )
        computed_minor, product_currency, computed_discount_minor, subtotal_minor, bump_minor = _compute_amount(payload, product)
        amount_minor = explicit_minor or computed_minor

        if amount_minor is None or amount_minor <= 0:
            return Response(
                {"detail": _("Payment amount missing or invalid.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload["amount_minor"] = int(amount_minor)
        payload["amount_cents"] = int(amount_minor)

        currency = (payload.get("currency") or product_currency or "mad").upper()
        payload["currency"] = currency
        payload["online_discount_minor"] = int(computed_discount_minor)
        payload["checkout_subtotal_minor"] = int(subtotal_minor)
        payload["checkout_bump_minor"] = int(bump_minor)

        if not payload.get("product_name") and product:
            payload["product_name"] = product.name
        if product and not payload.get("product_id"):
            payload["product_id"] = product.pk
        if not payload.get("email"):
            payload["email"] = f"guest+{uuid4().hex}@example.invalid"

        stripe_url = _create_stripe_session(payload, request)
        if stripe_url:
            return Response({"redirect_url": stripe_url}, status=status.HTTP_200_OK)

        mock_url = _build_mock_redirect_url(request)
        return Response({"redirect_url": mock_url}, status=status.HTTP_200_OK)
