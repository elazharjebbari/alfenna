from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Mapping, MutableMapping, Optional

from django.conf import settings

try:  # pragma: no cover - imported lazily in tests
    import stripe  # type: ignore
except Exception:  # pragma: no cover - stripe not installed in some environments
    stripe = None


def _digest(prefix: str, key: str) -> str:
    h = hashlib.sha1(key.encode("utf-8"))
    return f"{prefix}_{h.hexdigest()[:24]}"


@dataclass(frozen=True)
class StripeConfig:
    secret_key: str | None
    webhook_secret: str | None
    timeout: float = 10.0
    max_retries: int = 2

    @classmethod
    def from_settings(cls) -> "StripeConfig":
        return cls(
            secret_key=getattr(settings, "STRIPE_SECRET_KEY", None),
            webhook_secret=getattr(settings, "STRIPE_WEBHOOK_SECRET", None),
            timeout=float(getattr(settings, "STRIPE_HTTP_TIMEOUT", 10.0)),
            max_retries=int(getattr(settings, "STRIPE_MAX_RETRIES", 2)),
        )


class StripeClient:
    """Thin wrapper encapsulating retries, timeouts and offline fallback."""

    def __init__(
        self,
        config: StripeConfig,
        *,
        stripe_module: Any | None = None,
    ) -> None:
        self.config = config
        self._stripe = stripe_module or stripe
        if self._stripe is None and not self.offline_mode:
            raise RuntimeError("Stripe SDK is not installed but required for billing")

        if not self.offline_mode:
            self._stripe.api_key = config.secret_key
            if hasattr(self._stripe, "default_http_client") and hasattr(self._stripe, "http_client"):
                client = getattr(self._stripe.http_client, "RequestsClient", None)
                if client is not None:
                    self._stripe.default_http_client = client(timeout=config.timeout)

    @property
    def offline_mode(self) -> bool:
        return not self.config.secret_key

    # --- Payment intents -------------------------------------------------
    def create_payment_intent(
        self,
        *,
        amount: int,
        currency: str,
        idempotency_key: str,
        metadata: Optional[Mapping[str, Any]] = None,
        customer: str | None = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        payload: MutableMapping[str, Any] = {
            "amount": amount,
            "currency": currency.lower(),
            "metadata": dict(metadata or {}),
            **extra,
        }
        if customer:
            payload["customer"] = customer

        if self.offline_mode:
            intent_id = _digest("pi", idempotency_key)
            client_secret = _digest("cs_test", idempotency_key)
            payload.update({
                "id": intent_id,
                "client_secret": client_secret,
                "status": "requires_confirmation",
                "amount_received": 0,
            })
            return dict(payload)

        return self._execute(
            lambda: self._stripe.PaymentIntent.create(
                **payload,
                idempotency_key=idempotency_key,
            )
        )

    def confirm_payment_intent(self, intent_id: str, **kwargs: Any) -> Dict[str, Any]:
        if self.offline_mode:
            return {"id": intent_id, "status": "succeeded", **kwargs}
        return self._execute(lambda: self._stripe.PaymentIntent.confirm(intent_id, **kwargs))

    def retrieve_payment_intent(self, intent_id: str) -> Dict[str, Any]:
        if self.offline_mode:
            return {"id": intent_id, "status": "succeeded"}
        return self._execute(lambda: self._stripe.PaymentIntent.retrieve(intent_id))

    # --- Checkout sessions -----------------------------------------------
    def create_checkout_session(
        self,
        *,
        idempotency_key: str,
        **payload: Any,
    ) -> Dict[str, Any]:
        if self.offline_mode:
            session_id = _digest("cs", idempotency_key)
            fake = {
                "id": session_id,
                "url": payload.get("success_url", "https://example.com/success"),
                "payment_intent": _digest("pi", idempotency_key),
            }
            return fake

        return self._execute(
            lambda: self._stripe.checkout.Session.create(
                **payload,
                idempotency_key=idempotency_key,
            )
        )

    # --- Refunds ---------------------------------------------------------
    def create_refund(self, *, charge_id: str | None = None, intent_id: str | None = None, amount: int | None = None, idempotency_key: str | None = None, **extra: Any) -> Dict[str, Any]:
        if self.offline_mode:
            key = idempotency_key or (intent_id or charge_id or "refund")
            refund_id = _digest("re", key)
            return {
                "id": refund_id,
                "status": "succeeded",
                "amount": amount or 0,
                "payment_intent": intent_id,
                "charge": charge_id,
            }

        payload: MutableMapping[str, Any] = {}
        if charge_id:
            payload["charge"] = charge_id
        if intent_id:
            payload["payment_intent"] = intent_id
        if amount:
            payload["amount"] = amount
        payload.update(extra)
        return self._execute(
            lambda: self._stripe.Refund.create(
                **payload,
                idempotency_key=idempotency_key,
            )
        )

    # --- Webhooks --------------------------------------------------------
    def construct_event(self, payload: bytes, signature: str) -> Dict[str, Any]:
        if self.offline_mode:
            return json.loads(payload.decode("utf-8"))
        if not self.config.webhook_secret:
            raise RuntimeError("Stripe webhook secret missing")
        return self._stripe.Webhook.construct_event(
            payload=payload,
            sig_header=signature,
            secret=self.config.webhook_secret,
        )

    # --- Internal helpers ------------------------------------------------
    def _execute(self, fn: Any) -> Any:
        retries = max(self.config.max_retries, 0)
        delay = 0.5
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                return fn()
            except Exception as exc:  # pragma: no cover - network path
                last_exc = exc
                if attempt >= retries:
                    raise
                time.sleep(delay)
                delay *= 2
        if last_exc:
            raise last_exc
        raise RuntimeError("Stripe execution failed without exception")


def get_client() -> StripeClient:
    return StripeClient(StripeConfig.from_settings())
