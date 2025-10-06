"""Typed constants used across messaging endpoints."""
from __future__ import annotations

ACTIVATION_TTL_SECONDS = 24 * 3600
EMAIL_VERIFICATION_TTL_SECONDS = 24 * 3600
INVOICE_TTL_SECONDS = 24 * 3600
PASSWORD_RESET_TTL_SECONDS = 60 * 60  # 1 hour
UNSUBSCRIBE_TTL_SECONDS = 7 * 24 * 3600

TOKEN_NAMESPACE_ACCOUNTS = "accounts"
TOKEN_NAMESPACE_BILLING = "billing"
TOKEN_PURPOSE_VERIFY_EMAIL = "verify-email"
TOKEN_PURPOSE_UNSUBSCRIBE = "unsubscribe"
TOKEN_PURPOSE_ACTIVATION = "activation"
TOKEN_PURPOSE_INVOICE = "invoice"

DEFAULT_SITE_NAME = "Lumière Academy"
