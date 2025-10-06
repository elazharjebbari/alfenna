"""Celery tasks for the chatbot app."""

from __future__ import annotations

from datetime import timedelta
import logging

from celery import shared_task
from django.conf import settings
from django.utils import timezone

log = logging.getLogger("chatbot.service")


@shared_task(queue="default", ignore_result=True)
def purge_chat_messages_older_than(days: int | None = None) -> int:
    """Delete chat messages older than the retention policy."""

    from .models import ChatMessage

    retention_days = days if days is not None else getattr(settings, "CHATBOT_RETENTION_DAYS", 30)
    retention_days = max(int(retention_days), 0)
    if retention_days == 0:
        return 0

    cutoff = timezone.now() - timedelta(days=retention_days)
    deleted, _ = ChatMessage.objects.filter(created_at__lt=cutoff).delete()
    log.info(
        "chatbot_purge_task",
        extra={"deleted": deleted, "retention_days": retention_days},
    )
    return deleted
