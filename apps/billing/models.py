from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.catalog.models.models import Course


class OrderStatus(models.TextChoices):
    """State machine for orders.

    The enum is mirrored in ``apps.billing.domain.state`` where the transition
    table lives. We keep legacy aliases (``PENDING``/``FAILED``) so existing
    callers that still import those constants keep working while the new
    pipeline gradually rolls out.
    """

    DRAFT = "DRAFT", "Draft"
    PENDING_PAYMENT = "PENDING_PAYMENT", "Pending payment"
    REQUIRES_ACTION = "REQUIRES_ACTION", "Requires action"
    PAID = "PAID", "Paid"
    REFUNDED = "REFUNDED", "Refunded"
    CANCELED = "CANCELED", "Canceled"


# Legacy aliases kept for compatibility with pre-state-machine code paths.
OrderStatus.PENDING = OrderStatus.PENDING_PAYMENT  # type: ignore[attr-defined]
OrderStatus.FAILED = OrderStatus.CANCELED  # type: ignore[attr-defined]


class RefundStatus(models.TextChoices):
    REQUESTED = "REQUESTED", "Requested"
    SUCCEEDED = "SUCCEEDED", "Succeeded"
    FAILED = "FAILED", "Failed"


class InvoiceKind(models.TextChoices):
    INVOICE = "invoice", "Invoice"
    RECEIPT = "receipt", "Receipt"


class WebhookEventStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSED = "processed", "Processed"
    SKIPPED = "skipped", "Skipped"
    FAILED = "failed", "Failed"


def _default_idempotency_key() -> str:
    return f"order-{uuid.uuid4().hex}"


def _default_reference() -> str:
    return uuid.uuid4().hex[:24]


class CustomerProfile(models.Model):
    """Stripe customer information consolidated across guest/logged journeys."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="billing_profiles",
    )
    email = models.EmailField()
    stripe_customer_id = models.CharField(max_length=180, blank=True, default="")
    guest_id = models.CharField(max_length=64, blank=True, default="")
    merged_from_guest_id = models.CharField(max_length=64, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(user__isnull=False),
                name="billing_customer_unique_user",
            ),
            models.UniqueConstraint(
                fields=["stripe_customer_id"],
                condition=models.Q(stripe_customer_id__gt=""),
                name="billing_customer_unique_stripe_id",
            ),
        ]
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["guest_id"]),
            models.Index(fields=["created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        label = self.user.email if self.user_id and hasattr(self.user, "email") else self.email
        return f"CustomerProfile<{label or self.stripe_customer_id}>"

    def mark_guest_merge(self, guest_id: str) -> None:
        if guest_id and guest_id != self.merged_from_guest_id:
            self.merged_from_guest_id = guest_id
            self.save(update_fields=["merged_from_guest_id", "updated_at"])


class Order(models.Model):
    """Checkout order orchestrating Stripe and domain state transitions."""

    reference = models.CharField(max_length=32, unique=True, default=_default_reference)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="billing_orders",
    )
    customer_profile = models.ForeignKey(
        CustomerProfile,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="orders",
    )
    email = models.EmailField()

    course = models.ForeignKey(
        Course,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="orders",
    )
    price_plan = models.ForeignKey(
        "marketing.PricePlan",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="orders",
    )

    pricing_code = models.CharField(max_length=120, blank=True, default="")
    list_price_cents = models.PositiveIntegerField(default=0)
    discount_pct_effective = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    promo_code = models.CharField(max_length=80, blank=True, default="")

    currency = models.CharField(max_length=10, default="EUR")
    amount_subtotal = models.PositiveIntegerField(validators=[MinValueValidator(0)])
    tax_amount = models.PositiveIntegerField(default=0)
    amount_total = models.PositiveIntegerField(validators=[MinValueValidator(0)])

    status = models.CharField(max_length=32, choices=OrderStatus.choices, default=OrderStatus.DRAFT)
    version = models.PositiveIntegerField(default=1)

    stripe_checkout_session_id = models.CharField(max_length=200, blank=True, default="")
    stripe_payment_intent_id = models.CharField(max_length=200, blank=True, default="")
    stripe_customer_id = models.CharField(max_length=200, blank=True, default="")

    idempotency_key = models.CharField(max_length=200, unique=True, default=_default_idempotency_key)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["stripe_payment_intent_id"]),
            models.Index(fields=["stripe_checkout_session_id"]),
            models.Index(fields=["customer_profile"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover - trivial
        label = ""
        if self.price_plan_id and hasattr(self.price_plan, "slug"):
            label = f"plan:{self.price_plan.slug}"
        elif self.course_id and hasattr(self.course, "slug"):
            label = f"course:{self.course.slug}"
        else:
            label = "item:unknown"
        return f"Order#{self.id or '∅'} {label} {self.amount_total}{self.currency} {self.status}"

    def bump_version(self) -> None:
        self.version += 1
        self.save(update_fields=["version", "updated_at"])


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product_sku = models.CharField(max_length=120)
    quantity = models.PositiveIntegerField(default=1)
    unit_amount = models.PositiveIntegerField(validators=[MinValueValidator(0)])
    description = models.CharField(max_length=255, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["order", "product_sku"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"OrderItem(order={self.order_id}, sku={self.product_sku})"


class PaymentAttempt(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payment_attempts")
    intent_id = models.CharField(max_length=200)
    idempotency_key = models.CharField(max_length=200, unique=True)
    status = models.CharField(max_length=64, default="created")
    raw_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["intent_id"]),
            models.Index(fields=["status"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["order", "intent_id"], name="billing_unique_intent_per_order"),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"PaymentAttempt(order={self.order_id}, intent={self.intent_id})"


class Refund(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="refunds")
    refund_id = models.CharField(max_length=200, unique=True)
    amount = models.PositiveIntegerField(validators=[MinValueValidator(0)])
    status = models.CharField(max_length=32, choices=RefundStatus.choices)
    raw_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["refund_id"]),
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"Refund(order={self.order_id}, refund_id={self.refund_id}, amount={self.amount})"


class InvoiceArtifact(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="artifacts")
    kind = models.CharField(max_length=20, choices=InvoiceKind.choices)
    storage_path = models.CharField(max_length=255)
    checksum = models.CharField(max_length=128)
    rendered_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["order", "kind"],
                name="billing_unique_artifact_per_kind",
            )
        ]
        indexes = [models.Index(fields=["order", "kind"])]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"InvoiceArtifact(order={self.order_id}, kind={self.kind})"


class WebhookEvent(models.Model):
    event_id = models.CharField(max_length=200, unique=True)
    event_type = models.CharField(max_length=120)
    status = models.CharField(max_length=20, choices=WebhookEventStatus.choices, default=WebhookEventStatus.PENDING)
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.SET_NULL, related_name="webhook_events")
    correlation_id = models.CharField(max_length=64, blank=True, default="")
    raw_payload = models.JSONField(default=dict, blank=True)
    stripe_signature = models.CharField(max_length=255, blank=True, default="")
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    last_error = models.TextField(blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["event_type"]),
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
        ]
        ordering = ["-created_at"]

    def mark_processed(self) -> None:
        self.status = WebhookEventStatus.PROCESSED
        self.processed_at = timezone.now()
        self.last_error = ""
        self.save(update_fields=["status", "processed_at", "last_error", "updated_at"])


class Payment(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="payment")
    stripe_payment_intent_id = models.CharField(max_length=200)
    stripe_payment_method_id = models.CharField(max_length=200, blank=True, default="")
    latest_charge_id = models.CharField(max_length=200, blank=True, default="")
    status = models.CharField(max_length=50, default="succeeded")
    amount_received = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=10, default="EUR")
    idempotency_key = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["stripe_payment_intent_id"])]


class PaymentLog(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="logs")
    event_type = models.CharField(max_length=100)
    payload = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [models.Index(fields=["order", "event_type"])]


class Entitlement(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="entitlements")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="entitlements")
    granted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = [("user", "course")]
        indexes = [models.Index(fields=["user", "course"])]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"Entitlement({self.user_id} -> {self.course_id})"
