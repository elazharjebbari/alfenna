"""Domain integrations wiring messaging with external apps (e.g. billing)."""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Tuple
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts.models import StudentProfile
from apps.billing.services.invoice import build_invoice_url

from .constants import (
    ACTIVATION_TTL_SECONDS,
    DEFAULT_SITE_NAME,
    INVOICE_TTL_SECONDS,
    TOKEN_NAMESPACE_ACCOUNTS,
    TOKEN_NAMESPACE_BILLING,
    TOKEN_PURPOSE_ACTIVATION,
    TOKEN_PURPOSE_INVOICE,
)
from .services import EmailService
from .tokens import TokenService
from .utils import secure_base_url

log = logging.getLogger("messaging.integrations")
UserModel = get_user_model()


def _site_name() -> str:
    return getattr(settings, "SITE_NAME", settings.SEO_DEFAULTS.get("site_name", DEFAULT_SITE_NAME))


def _support_email() -> str:
    return getattr(settings, "SUPPORT_EMAIL", settings.DEFAULT_FROM_EMAIL)


def _primary_recipient(order) -> str | None:
    if getattr(order, "email", None):
        return order.email
    user = getattr(order, "user", None)
    if user and user.email:
        return user.email
    return None


def _first_name(order) -> str:
    user = getattr(order, "user", None)
    if user and user.first_name:
        return user.first_name
    recipient = _primary_recipient(order)
    if recipient:
        return recipient.split("@", 1)[0]
    return ""  # fallback to empty string


def enqueue_account_activation(order) -> None:
    user = getattr(order, "user", None)
    recipient = _primary_recipient(order)
    if not user or not recipient:
        log.info("activation_skip_missing_user", extra={"order_id": getattr(order, "id", None)})
        return

    token = TokenService.make_signed(
        namespace=TOKEN_NAMESPACE_ACCOUNTS,
        purpose=TOKEN_PURPOSE_ACTIVATION,
        claims={"user_id": user.id, "order_id": order.id},
    )
    activation_url = f"{secure_base_url()}/accounts/activate/?{urlencode({'t': token})}"

    EmailService.compose_and_enqueue(
        namespace="accounts",
        purpose="activation",
        template_slug="accounts/activation",
        to=[recipient],
        dedup_key=f"order:{order.id}:activation",
        context={
            "user_first_name": _first_name(order),
            "activation_url": activation_url,
            "activation_ttl_hours": ACTIVATION_TTL_SECONDS // 3600,
            "site_name": _site_name(),
            "support_email": _support_email(),
        },
        metadata={"order_id": order.id},
    )
    log.info("activation_email_enqueued", extra={"order_id": order.id})


def enqueue_invoice_ready(order, *, invoice_url: str | None = None, artifact_signature: str | None = None) -> None:
    recipient = _primary_recipient(order)
    if not recipient:
        log.info("invoice_skip_missing_email", extra={"order_id": getattr(order, "id", None)})
        return

    invoice_url = invoice_url or build_invoice_url(order)
    amount_total = Decimal(getattr(order, "amount_total", 0) or 0) / Decimal("100")
    currency = getattr(order, "currency", "EUR").upper()
    reference = order.reference or str(order.id)
    dedup_key = artifact_signature or reference or str(order.id)

    invoice_date = timezone.localtime(getattr(order, "created_at", timezone.now()))
    invoice_ttl_hours = getattr(settings, "BILLING_INVOICE_TOKEN_TTL", INVOICE_TTL_SECONDS) // 3600
    first_name = _first_name(order)

    EmailService.compose_and_enqueue(
        namespace="billing",
        purpose="invoice_ready",
        template_slug="billing/invoice",
        to=[recipient],
        dedup_key=f"invoice:{order.id}:{dedup_key}",
        context={
            # historic context (kept for console/debug consumers)
            "customer_name": first_name,
            "order_reference": reference,
            "amount_total": f"{amount_total:.2f}",
            "currency": currency,
            "amount_total_display": f"{amount_total:.2f} {currency}",
            # template fields
            "user_first_name": first_name,
            "invoice_number": reference,
            "invoice_amount": f"{amount_total:.2f} {currency}",
            "invoice_date": invoice_date.strftime("%d/%m/%Y"),
            "invoice_url": invoice_url,
            "site_name": _site_name(),
            "invoice_ttl_hours": invoice_ttl_hours,
        },
        metadata={
            "order_id": order.id,
            "invoice_signature": artifact_signature or "",
        },
    )
    log.info("invoice_email_enqueued", extra={"order_id": order.id})


def _normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def _generate_username(email: str) -> str:
    base = slugify(email.split("@", 1)[0]) or "user"
    base = base[:20] or "user"
    candidate = base
    suffix = 1
    while UserModel.objects.filter(username=candidate).exists():
        candidate = f"{base}{suffix}"
        suffix += 1
        if len(candidate) > 150:
            candidate = candidate[:150]
    return candidate


def _ensure_profile(user) -> None:
    StudentProfile.objects.get_or_create(user=user)


def _provision_order_user(order) -> Tuple[Any | None, bool]:
    email = _normalize_email(_primary_recipient(order))
    if not email:
        log.info("order_user_provision_skipped", extra={"order_id": getattr(order, "id", None)})
        return None, False

    with transaction.atomic():
        user = (
            UserModel.objects.select_for_update()
            .filter(email__iexact=email)
            .first()
        )
        created = False
        if not user:
            username = _generate_username(email)
            user = UserModel.objects.create_user(username=username, email=email)
            created = True

        original_active = user.is_active
        original_has_password = user.has_usable_password()

        updates = []
        if not user.is_active:
            user.is_active = True
            updates.append("is_active")
        if not original_has_password:
            user.set_unusable_password()
            updates.append("password")
        if updates:
            user.save(update_fields=updates)

        _ensure_profile(user)

        normalized_email = user.email or email
        order_user_changed = order.user_id != user.id
        email_changed = _normalize_email(order.email) != _normalize_email(normalized_email)
        if order_user_changed or email_changed:
            order.user = user
            order.email = normalized_email
            order.save(update_fields=["user", "email"])

    activation_required = created or not original_active or not original_has_password
    return user, activation_required


def notify_order_paid(order) -> None:
    """Enqueue transactional messaging when an order transitions to paid."""
    activation_required = False
    user = getattr(order, "user", None)
    if user and user.is_active and user.has_usable_password():
        activation_required = False
    else:
        try:
            user, activation_required = _provision_order_user(order)
        except IntegrityError:
            log.exception("order_user_provision_integrity", extra={"order_id": getattr(order, "id", None)})
        except Exception:
            log.exception("order_user_provision_failed", extra={"order_id": getattr(order, "id", None)})
            activation_required = False

    if activation_required:
        try:
            enqueue_account_activation(order)
        except Exception:
            log.exception("activation_email_failed", extra={"order_id": getattr(order, "id", None)})
    else:
        log.info(
            "activation_skipped",
            extra={
                "order_id": getattr(order, "id", None),
                "user_id": getattr(user, "id", None) if user else None,
            },
        )
    log.info(
        "invoice_email_deferred",
        extra={"order_id": getattr(order, "id", None)},
    )
