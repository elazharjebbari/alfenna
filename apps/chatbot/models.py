"""Database models for the chatbot domain."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    """Reusable timestamp mixin."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ChatSession(TimeStampedModel):
    """Represents a conversational session on the website."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="chat_sessions",
    )
    session_key = models.CharField(max_length=64, unique=True)
    consent_snapshot = models.CharField(max_length=1, default="N")
    locale = models.CharField(max_length=8, default="fr")
    last_activity = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"ChatSession({self.session_key})"


class ChatMessage(TimeStampedModel):
    """Single message exchanged during a session."""

    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_SYSTEM = "system"
    ROLE_CHOICES = (
        (ROLE_USER, "User"),
        (ROLE_ASSISTANT, "Assistant"),
        (ROLE_SYSTEM, "System"),
    )

    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    content = models.TextField()
    tokens_in = models.PositiveIntegerField(null=True, blank=True)
    tokens_out = models.PositiveIntegerField(null=True, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ("created_at",)

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"ChatMessage({self.role})"


class ConsentEvent(models.Model):
    """Audit trail of consent opt-in/out events."""

    VALUE_CHOICES = (
        ("Y", "Yes"),
        ("N", "No"),
    )

    session = models.ForeignKey(
        ChatSession,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="consent_events",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="chat_consent_events",
    )
    value = models.CharField(max_length=1, choices=VALUE_CHOICES)
    ip = models.CharField(max_length=64, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"ConsentEvent(value={self.value})"


class ProviderCall(TimeStampedModel):
    """Minimal audit entry for upstream provider interactions."""

    STATUS_PENDING = "pending"
    STATUS_SUCCESS = "success"
    STATUS_ERROR = "error"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_ERROR, "Error"),
    )

    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name="provider_calls",
    )
    provider = models.CharField(max_length=32)
    model = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    request_hash = models.CharField(max_length=64, db_index=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:  # pragma: no cover - admin display
        return f"ProviderCall(provider={self.provider}, status={self.status})"
