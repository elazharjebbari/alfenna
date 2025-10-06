from __future__ import annotations

import logging
from typing import Any, Dict
from uuid import uuid4

from django.conf import settings
from django.utils.http import urlencode
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.leads.permissions import PublicPOSTOnly

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


class CheckoutSessionView(APIView):
    """Create a checkout session for online payments."""

    permission_classes = [PublicPOSTOnly]
    authentication_classes: list[Any] = []

    def post(self, request, *args, **kwargs):
        payload = request.data if isinstance(request.data, dict) else {}
        payment_method = str(payload.get("payment_method", "")).lower()

        if payment_method != "online":
            return Response(
                {"detail": _("payment_method must be 'online'.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        stripe_url = _create_stripe_session(payload, request)
        if stripe_url:
            return Response({"redirect_url": stripe_url}, status=status.HTTP_200_OK)

        mock_url = _build_mock_redirect_url(request)
        return Response({"redirect_url": mock_url}, status=status.HTTP_200_OK)
