"""Database models for Google Ads server-side uploads."""

from __future__ import annotations

from django.db import models
from django.utils import timezone


class ConversionRecordQuerySet(models.QuerySet):
    def pending(self) -> "ConversionRecordQuerySet":
        return self.filter(status=ConversionRecord.Status.PENDING)

    def sent(self) -> "ConversionRecordQuerySet":
        return self.filter(status=ConversionRecord.Status.SENT)

    def held(self) -> "ConversionRecordQuerySet":
        return self.filter(status=ConversionRecord.Status.HELD)


class ConversionRecord(models.Model):
    """Outbox entry capturing a Google Ads conversion upload attempt."""

    class Kind(models.TextChoices):
        LEAD = "lead", "Lead"
        PURCHASE = "purchase", "Purchase"
        ADJUSTMENT = "adjustment", "Adjustment"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        HELD = "HELD", "Held"
        SENT = "SENT", "Sent"
        ERROR = "ERROR", "Error"
        SKIPPED_NO_CONSENT = "SKIPPED_NO_CONSENT", "Skipped (no consent)"

    kind = models.CharField(max_length=32, choices=Kind.choices)
    action_key = models.CharField(max_length=64)
    order_id = models.CharField(max_length=128, blank=True, null=True)
    lead_id = models.CharField(max_length=128, blank=True, null=True)

    gclid = models.CharField(max_length=255, blank=True, null=True)
    gbraid = models.CharField(max_length=255, blank=True, null=True)
    wbraid = models.CharField(max_length=255, blank=True, null=True)
    gclsrc = models.CharField(max_length=100, blank=True, null=True)

    value = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    currency = models.CharField(max_length=16, default="EUR")
    event_at = models.DateTimeField(default=timezone.now)

    enhanced_identifiers = models.JSONField(default=dict, blank=True)
    adjustment_type = models.CharField(max_length=32, blank=True, null=True)

    idempotency_key = models.CharField(max_length=160, unique=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)
    attempt_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, null=True)
    google_upload_status = models.JSONField(default=dict, blank=True)
    hold_reason = models.CharField(max_length=255, blank=True, default="")
    effective_mode = models.CharField(max_length=16, default="on")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ConversionRecordQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["status"], name="adsbridge_status_idx"),
            models.Index(fields=["order_id"], name="adsbridge_order_idx"),
            models.Index(fields=["action_key"], name="adsbridge_action_idx"),
        ]
        verbose_name = "Google Ads conversion record"
        verbose_name_plural = "Google Ads conversion records"

    def mark_sent(self, payload: dict | None = None, *, mode: str | None = None) -> None:
        self.status = self.Status.SENT
        if payload is not None:
            self.google_upload_status = payload
        self.last_error = ""
        self.hold_reason = ""
        updates = ["status", "google_upload_status", "last_error", "hold_reason", "updated_at"]
        if mode:
            self.effective_mode = mode
            updates.append("effective_mode")
        self.save(update_fields=updates)

    def mark_error(
        self,
        message: str,
        *,
        mode: str | None = None,
        payload: dict | None = None,
    ) -> None:
        self.status = self.Status.ERROR
        self.last_error = message
        if payload is not None:
            self.google_upload_status = payload
        if mode:
            self.effective_mode = mode
        self.hold_reason = ""
        updates = ["status", "last_error", "hold_reason", "updated_at"]
        if payload is not None:
            updates.append("google_upload_status")
        if mode:
            updates.append("effective_mode")
        self.save(update_fields=updates)

    def mark_skipped(self, reason: str, *, mode: str | None = None) -> None:
        self.status = self.Status.SKIPPED_NO_CONSENT
        self.last_error = reason
        self.hold_reason = ""
        updates = ["status", "last_error", "hold_reason", "updated_at"]
        if mode:
            self.effective_mode = mode
            updates.append("effective_mode")
        self.save(update_fields=updates)

    def mark_held(self, reason: str, *, mode: str) -> None:
        self.status = self.Status.HELD
        self.hold_reason = reason
        self.last_error = reason
        self.effective_mode = mode
        self.save(update_fields=["status", "hold_reason", "last_error", "effective_mode", "updated_at"])

    def increment_attempts(self, *, mode: str | None = None) -> None:
        self.attempt_count += 1
        updates = ["attempt_count", "updated_at"]
        if mode:
            self.effective_mode = mode
            updates.append("effective_mode")
        self.save(update_fields=updates)
