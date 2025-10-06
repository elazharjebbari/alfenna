"""Billing/Stripe specific configuration knobs.

This module is imported from base settings so all environments share a
single source of truth for billing toggles and Stripe credentials.
"""

from __future__ import annotations

import os
from typing import Final

_TRUE_VALUES: Final[set[str]] = {"1", "true", "yes", "y", "on"}


def _env_flag(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in _TRUE_VALUES


# Feature toggle -----------------------------------------------------------------------
BILLING_ENABLED: Final[bool] = _env_flag("BILLING_ENABLED", default=True)
INVOICING_ENABLED: Final[bool] = _env_flag("INVOICING_ENABLED", default=True)

# Signed link configuration ------------------------------------------------------------
BILLING_INVOICE_TOKEN_TTL: Final[int] = int(os.getenv("BILLING_INVOICE_TOKEN_TTL", str(60 * 60 * 24 * 14)))
BILLING_INVOICE_TOKEN_NAMESPACE: Final[str] = os.getenv("BILLING_INVOICE_TOKEN_NAMESPACE", "billing")
BILLING_INVOICE_TOKEN_PURPOSE: Final[str] = os.getenv("BILLING_INVOICE_TOKEN_PURPOSE", "invoice_download")

# Stripe credentials / HTTP client -----------------------------------------------------
STRIPE_SECRET_KEY: Final[str] = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY: Final[str] = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET: Final[str] = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_HTTP_TIMEOUT: Final[float] = float(os.getenv("STRIPE_HTTP_TIMEOUT", "10"))
STRIPE_MAX_RETRIES: Final[int] = int(os.getenv("STRIPE_MAX_RETRIES", "2"))

# Storage / artefacts ------------------------------------------------------------------
BILLING_INVOICE_ROOT: Final[str] = os.getenv("BILLING_INVOICE_ROOT", "billing/invoices")

# Observability ------------------------------------------------------------------------
BILLING_REQUEST_ID_HEADER: Final[str] = os.getenv("BILLING_REQUEST_ID_HEADER", "HTTP_X_REQUEST_ID")
BILLING_METRICS_NAMESPACE: Final[str] = os.getenv("BILLING_METRICS_NAMESPACE", "billing")
BILLING_LOG_JSON: Final[bool] = _env_flag("BILLING_LOG_JSON", default=True)

# Webhooks -----------------------------------------------------------------------------
BILLING_WEBHOOK_REPLAY_STRATEGY: Final[str] = os.getenv("BILLING_WEBHOOK_REPLAY_STRATEGY", "idempotent")
BILLING_WEBHOOK_RETRY_LIMIT: Final[int] = int(os.getenv("BILLING_WEBHOOK_RETRY_LIMIT", "3"))

__all__ = [
    "BILLING_ENABLED",
    "INVOICING_ENABLED",
    "STRIPE_SECRET_KEY",
    "STRIPE_PUBLISHABLE_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "STRIPE_HTTP_TIMEOUT",
    "STRIPE_MAX_RETRIES",
    "BILLING_INVOICE_ROOT",
    "BILLING_INVOICE_TOKEN_TTL",
    "BILLING_INVOICE_TOKEN_NAMESPACE",
    "BILLING_INVOICE_TOKEN_PURPOSE",
    "BILLING_REQUEST_ID_HEADER",
    "BILLING_METRICS_NAMESPACE",
    "BILLING_LOG_JSON",
    "BILLING_WEBHOOK_REPLAY_STRATEGY",
    "BILLING_WEBHOOK_RETRY_LIMIT",
]
