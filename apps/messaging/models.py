"""Database structures backing the transactional messaging system."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

from django.conf import settings
from django.db import models
from django.utils import timezone


class OutboxEmailQuerySet(models.QuerySet):
    """Custom queryset with helpers used by Celery tasks and services."""

    def queued(self) -> "OutboxEmailQuerySet":
        return self.filter(
            status__in=[OutboxEmail.Status.QUEUED, OutboxEmail.Status.RETRYING]
        )

    def due(self, *, as_of: Optional[datetime] = None) -> "OutboxEmailQuerySet":
        reference = as_of or timezone.now()
        return self.queued().filter(scheduled_at__lte=reference)

    def due_ordered(self, *, as_of: Optional[datetime] = None) -> "OutboxEmailQuerySet":
        return self.due(as_of=as_of).order_by("priority", "scheduled_at", "id")

    def for_namespace(self, namespace: str) -> "OutboxEmailQuerySet":
        return self.filter(namespace=namespace)


class OutboxEmail(models.Model):
    """Pending or historical email ready to be processed by Celery."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RETRYING = "retrying", "Retrying"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        SUPPRESSED = "suppressed", "Suppressed"

    objects = OutboxEmailQuerySet.as_manager()

    namespace = models.CharField(max_length=64)
    purpose = models.CharField(max_length=64)
    dedup_key = models.CharField(max_length=128)
    flow_id = models.CharField(max_length=32, blank=True, default="", db_index=True)
    to = models.JSONField(default=list, blank=True)
    cc = models.JSONField(default=list, blank=True)
    bcc = models.JSONField(default=list, blank=True)
    reply_to = models.JSONField(default=list, blank=True)
    locale = models.CharField(max_length=12, default="fr")
    template_slug = models.CharField(max_length=128)
    template_version = models.PositiveIntegerField(default=1)
    subject_override = models.CharField(max_length=255, blank=True)
    rendered_subject = models.CharField(max_length=255, blank=True, default="")
    rendered_html = models.TextField(blank=True, default="")
    rendered_text = models.TextField(blank=True, default="")
    context = models.JSONField(default=dict, blank=True)
    headers = models.JSONField(default=dict, blank=True)
    attachments = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    priority = models.PositiveSmallIntegerField(default=100)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    scheduled_at = models.DateTimeField(default=timezone.now)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.CharField(max_length=64, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    last_error_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True)
    last_error_message = models.CharField(max_length=512, blank=True)
    provider_message_id = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["namespace", "dedup_key"],
                name="uniq_outbox_namespace_dedup_key",
            )
        ]
        indexes = [
            models.Index(fields=["status", "scheduled_at"], name="outbox_status_schedule_idx"),
            models.Index(fields=["namespace", "status"], name="outbox_namespace_status_idx"),
            models.Index(fields=["locked_at"], name="outbox_locked_idx"),
        ]
        verbose_name = "Outbox email"
        verbose_name_plural = "Outbox emails"

    def mark_sent(self, *, provider_id: Optional[str] = None) -> None:
        self.status = self.Status.SENT
        self.sent_at = timezone.now()
        self.locked_at = None
        self.locked_by = ""
        self.next_attempt_at = None
        self.last_error_code = ""
        self.last_error_message = ""
        if provider_id:
            self.provider_message_id = provider_id
        self.save(
            update_fields=[
                "status",
                "sent_at",
                "provider_message_id",
                "locked_at",
                "locked_by",
                "next_attempt_at",
                "last_error_code",
                "last_error_message",
                "updated_at",
            ]
        )

    def mark_failed(self, *, code: str = "", message: str = "") -> None:
        self.status = self.Status.FAILED
        self.last_error_at = timezone.now()
        self.last_error_code = code[:64]
        self.last_error_message = message[:512]
        self.save(
            update_fields=[
                "status",
                "last_error_at",
                "last_error_code",
                "last_error_message",
                "updated_at",
            ]
        )

    @property
    def primary_recipient(self) -> str:
        recipients: Iterable[str] = self.to or []
        return next(iter(recipients), "")


class EmailAttempt(models.Model):
    """Audit trail of delivery tries for a given OutboxEmail."""

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILURE = "failure", "Failure"
        RETRY = "retry", "Retry"

    outbox = models.ForeignKey(OutboxEmail, related_name="attempts", on_delete=models.CASCADE)
    status = models.CharField(max_length=16, choices=Status.choices)
    provider_message_id = models.CharField(max_length=255, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    error_message = models.CharField(max_length=512, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["outbox_id", "created_at"], name="attempt_outbox_created_idx"),
        ]
        verbose_name = "Email attempt"
        verbose_name_plural = "Email attempts"


class EmailTemplateQuerySet(models.QuerySet):
    def active(self) -> "EmailTemplateQuerySet":
        return self.filter(is_active=True)

    def latest_for(self, slug: str, locale: str) -> Optional["EmailTemplate"]:
        preferred_locales = [locale]
        default_locale = getattr(settings, "LANGUAGE_CODE", "en")
        if default_locale:
            preferred_locales.append(default_locale)
        preferred_locales.append("en")
        # Remove duplicates while preserving order
        seen = []
        ordered_locales = []
        for loc in preferred_locales:
            if loc not in seen:
                seen.append(loc)
                ordered_locales.append(loc)

        for loc in ordered_locales:
            template = (
                self.active()
                .filter(slug=slug, locale=loc)
                .order_by("-version")
                .first()
            )
            if template is not None:
                return template
        return None


class EmailTemplate(models.Model):
    """Versioned template stored in database for transactional messaging."""

    objects = EmailTemplateQuerySet.as_manager()

    slug = models.SlugField(max_length=128)
    locale = models.CharField(max_length=12, default="fr")
    version = models.PositiveIntegerField(default=1)
    subject = models.CharField(max_length=255)
    html_template = models.TextField()
    text_template = models.TextField()
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["slug", "locale", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["slug", "locale", "version"],
                name="uniq_email_template_version",
            )
        ]
        indexes = [
            models.Index(fields=["slug", "locale"], name="template_slug_locale_idx"),
            models.Index(fields=["is_active"], name="template_active_idx"),
        ]
        verbose_name = "Email template"
        verbose_name_plural = "Email templates"

    def __str__(self) -> str:  # pragma: no cover - human readable only
        return f"{self.slug} v{self.version} ({self.locale})"


class CampaignQuerySet(models.QuerySet):
    def scheduled(self) -> "CampaignQuerySet":
        return self.filter(status=Campaign.Status.SCHEDULED)

    def due(self, *, as_of: Optional[datetime] = None) -> "CampaignQuerySet":
        reference = as_of or timezone.now()
        return self.scheduled().filter(scheduled_at__lte=reference)


class Campaign(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SCHEDULED = "scheduled", "Scheduled"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        PAUSED = "paused", "Paused"

    objects = CampaignQuerySet.as_manager()

    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=160, unique=True)
    template_slug = models.CharField(max_length=128)
    locale = models.CharField(max_length=12, default="fr")
    subject_override = models.CharField(max_length=255, blank=True, default="")
    scheduled_at = models.DateTimeField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    batch_size = models.PositiveIntegerField(default=500)
    dry_run = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-scheduled_at"]
        indexes = [
            models.Index(fields=["status", "scheduled_at"], name="campaign_status_sched_idx"),
        ]

    def __str__(self) -> str:  # pragma: no cover - human-readable
        return f"Campaign<{self.slug} {self.status}>"


class CampaignRecipient(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent"
        SUPPRESSED = "suppressed", "Suppressed"

    campaign = models.ForeignKey(Campaign, related_name="recipients", on_delete=models.CASCADE)
    email = models.EmailField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    locale = models.CharField(max_length=12, default="fr")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    last_enqueued_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["campaign", "email"], name="uniq_campaign_email"),
        ]
        indexes = [
            models.Index(fields=["campaign", "status"], name="campaign_recipient_status_idx"),
        ]

    def mark_enqueued(self) -> None:
        self.status = self.Status.QUEUED
        self.last_enqueued_at = timezone.now()
        self.save(update_fields=["status", "last_enqueued_at", "updated_at"])
