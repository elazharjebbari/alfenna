"""Celery tasks responsible for draining and delivering transactional emails."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Iterable, List

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import connection, transaction
from django.utils import timezone

from .campaigns import CampaignService
from .exceptions import TemplateNotFoundError
from .models import Campaign, EmailAttempt, OutboxEmail
from .services import EmailService, TemplateService
from . import metrics as messaging_metrics

from smtplib import SMTPRecipientsRefused

log = logging.getLogger("messaging.tasks")


DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_RETRY_INTERVAL_SECONDS = 5 * 60


def _retry_config() -> tuple[int, int]:
    max_attempts = getattr(settings, "PASSWORD_RESET_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS)
    interval = getattr(
        settings,
        "PASSWORD_RESET_RETRY_INTERVAL_SECONDS",
        DEFAULT_RETRY_INTERVAL_SECONDS,
    )
    return max(max_attempts, 1), max(interval, 60)


def _classify_smtp_error(exc: Exception) -> str:
    message = str(exc)
    message_lower = message.lower()
    if isinstance(exc, SMTPRecipientsRefused):  # pragma: no cover - exercised via tests
        for code, detail in exc.recipients.values():
            text = detail.decode("utf-8", "ignore") if isinstance(detail, bytes) else str(detail)
            combined = f"{code} {text}".lower()
            if "bounce" in combined and "limit" in combined:
                return "bounce_limit"
            if "5.1.1" in combined or "user unknown" in combined:
                return "recipient_unknown"
        if any(
            "bounce" in (str(detail).lower() if not isinstance(detail, bytes) else detail.decode("utf-8", "ignore").lower())
            and "limit" in (str(detail).lower() if not isinstance(detail, bytes) else detail.decode("utf-8", "ignore").lower())
            for _, detail in exc.recipients.values()
        ):
            return "bounce_limit"
    if "bounce" in message_lower and "limit" in message_lower:
        return "bounce_limit"
    if "5.1.1" in message_lower or "user unknown" in message_lower:
        return "recipient_unknown"
    return "smtp_error"


def _should_retry(classification: str) -> bool:
    return classification in {"bounce_limit", "smtp_error"}


def _attachments_payload(raw: Iterable[dict]) -> List[tuple]:
    payload = []
    for item in raw:
        try:
            name = item["name"]
            content = item["content"]
            mimetype = item.get("mime_type", "application/octet-stream")
        except Exception:  # pragma: no cover - defensive
            continue
        payload.append((name, content, mimetype))
    return payload


def _build_message(outbox: OutboxEmail) -> EmailMultiAlternatives:
    message = EmailMultiAlternatives(
        subject=outbox.rendered_subject or outbox.subject_override or "",
        body=outbox.rendered_text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=outbox.to,
        cc=outbox.cc,
        bcc=outbox.bcc,
        reply_to=outbox.reply_to,
        headers=outbox.headers,
    )
    if outbox.rendered_html:
        message.attach_alternative(outbox.rendered_html, "text/html")
    for attachment in _attachments_payload(outbox.attachments):
        message.attach(*attachment)
    return message


def _update_retry_state(
    outbox: OutboxEmail,
    *,
    classification: str,
    error: str,
    next_eta: datetime,
) -> None:
    outbox.last_error_at = timezone.now()
    outbox.last_error_code = classification[:64]
    outbox.last_error_message = error[:512]
    outbox.status = OutboxEmail.Status.RETRYING
    outbox.locked_at = None
    outbox.locked_by = ""
    outbox.next_attempt_at = next_eta
    outbox.scheduled_at = next_eta
    outbox.save(
        update_fields=[
            "last_error_at",
            "last_error_code",
            "last_error_message",
            "status",
            "locked_at",
            "locked_by",
            "next_attempt_at",
            "scheduled_at",
            "updated_at",
        ]
    )


def _update_terminal_state(outbox: OutboxEmail, *, classification: str, error: str) -> None:
    outbox.last_error_at = timezone.now()
    outbox.last_error_code = classification[:64]
    outbox.last_error_message = error[:512]
    outbox.status = OutboxEmail.Status.SUPPRESSED
    outbox.locked_at = None
    outbox.locked_by = ""
    outbox.next_attempt_at = None
    outbox.save(
        update_fields=[
            "last_error_at",
            "last_error_code",
            "last_error_message",
            "status",
            "locked_at",
            "locked_by",
            "next_attempt_at",
            "updated_at",
        ]
    )


@shared_task(bind=True, max_retries=4, acks_late=True)
def send_outbox_email(self, outbox_id: int) -> None:
    """Send a single OutboxEmail and record the attempt."""

    start = timezone.now()
    try:
        with transaction.atomic():
            outbox = OutboxEmail.objects.select_for_update().get(pk=outbox_id)
            outbox.attempt_count += 1
            outbox.locked_at = timezone.now()
            outbox.locked_by = f"send:{self.request.id}"
            outbox.save(update_fields=["attempt_count", "locked_at", "locked_by", "updated_at"])
    except OutboxEmail.DoesNotExist:  # pragma: no cover - defensive
        log.warning("missing_outbox", extra={"outbox_id": outbox_id})
        return

    if outbox.status == OutboxEmail.Status.SENT:
        log.info("outbox_already_sent", extra={"outbox_id": outbox_id})
        return

    max_attempts, retry_interval = _retry_config()

    try:
        message = _build_message(outbox)
        sent = get_connection().send_messages([message])
        provider_id = getattr(message, "extra_headers", {}).get("Message-ID", "")
    except Exception as exc:
        error_message = str(exc)
        classification = _classify_smtp_error(exc)
        _record_attempt(
            outbox,
            status=EmailAttempt.Status.FAILURE,
            error_message=error_message,
            started_at=start,
        )

        if _should_retry(classification) and outbox.attempt_count < max_attempts:
            next_eta = timezone.now() + timedelta(seconds=retry_interval)
            _update_retry_state(outbox, classification=classification, error=error_message, next_eta=next_eta)
            log.info(
                "outbox_retry_scheduled",
                extra={
                    "outbox_id": outbox.id,
                    "flow_id": outbox.flow_id,
                    "attempt": outbox.attempt_count,
                    "classification": classification,
                    "next_eta": next_eta.isoformat(),
                },
            )
            raise self.retry(exc=exc, countdown=retry_interval)

        _update_terminal_state(outbox, classification=classification, error=error_message)
        log.warning(
            "outbox_terminal",
            extra={
                "outbox_id": outbox.id,
                "flow_id": outbox.flow_id,
                "classification": classification,
                "attempt": outbox.attempt_count,
            },
        )
        messaging_metrics.record_password_reset_event(classification)
        return

    if sent:
        outbox.mark_sent(provider_id=provider_id)
        _record_attempt(
            outbox,
            status=EmailAttempt.Status.SUCCESS,
            started_at=start,
        )
        log.info("outbox_sent", extra={"outbox_id": outbox_id, "flow_id": outbox.flow_id})
        messaging_metrics.record_password_reset_event("sent")
    else:  # pragma: no cover - defensive
        error = "SMTP backend returned 0"
        _record_attempt(
            outbox,
            status=EmailAttempt.Status.FAILURE,
            error_message=error,
            started_at=start,
        )
        if outbox.attempt_count < max_attempts:
            next_eta = timezone.now() + timedelta(seconds=retry_interval)
            _update_retry_state(outbox, classification="smtp_error", error=error, next_eta=next_eta)
            log.warning(
                "outbox_retry_scheduled",
                extra={
                    "outbox_id": outbox.id,
                    "flow_id": outbox.flow_id,
                    "attempt": outbox.attempt_count,
                    "classification": "smtp_error",
                    "next_eta": next_eta.isoformat(),
                },
            )
            raise self.retry(exc=RuntimeError(error), countdown=retry_interval)

        _update_terminal_state(outbox, classification="smtp_error", error=error)
        log.warning(
            "outbox_terminal",
            extra={
                "outbox_id": outbox.id,
                "flow_id": outbox.flow_id,
                "classification": "smtp_error",
                "attempt": outbox.attempt_count,
            },
        )
        messaging_metrics.record_password_reset_event("smtp_error")
        return


def _record_attempt(
    outbox: OutboxEmail,
    *,
    status: str,
    started_at: datetime,
    error_message: str | None = None,
) -> None:
    EmailAttempt.objects.create(
        outbox=outbox,
        status=status,
        error_message=error_message or "",
        duration_ms=int((timezone.now() - started_at).total_seconds() * 1000),
    )
@shared_task(bind=True, ignore_result=True, acks_late=True)
def drain_outbox_batch(self, limit: int = 100) -> None:
    """Fetch queued emails, mark them as sending, and trigger send tasks."""

    now = timezone.now()
    worker_id = f"drain:{self.request.id}"
    ids: List[int]

    if connection.vendor == "sqlite":
        ids = list(
            OutboxEmail.objects.due_ordered(as_of=now)
            .filter(locked_at__isnull=True)
            .values_list("id", flat=True)[:limit]
        )
        OutboxEmail.objects.filter(id__in=ids).update(
            status=OutboxEmail.Status.SENDING,
            locked_at=now,
            locked_by=worker_id,
        )
    else:
        with transaction.atomic():
            due = (
                OutboxEmail.objects.due_ordered(as_of=now)
                .select_for_update(skip_locked=True)
                .filter(locked_at__isnull=True)[:limit]
            )
            ids = list(due.values_list("id", flat=True))
            if ids:
                OutboxEmail.objects.filter(id__in=ids).update(
                    status=OutboxEmail.Status.SENDING,
                    locked_at=now,
                    locked_by=worker_id,
                )

    if not ids:
        log.debug("outbox_empty", extra={"limit": limit})
        return

    for outbox_id in ids:
        send_outbox_email.delay(outbox_id)

    log.info("outbox_batch_scheduled", extra={"count": len(ids)})


@shared_task(bind=True, ignore_result=True)
def enqueue_render_from_template(
    self,
    *,
    namespace: str,
    purpose: str,
    template_slug: str,
    to: Iterable[str],
    locale: str = "fr",
    language: str | None = None,
    context: dict | None = None,
    dedup_key: str | None = None,
    scheduled_at: datetime | None = None,
    priority: int = 100,
) -> int:
    """Helper task allowing other apps to enqueue using Celery chains."""

    try:
        outbox = EmailService.compose_and_enqueue(
            namespace=namespace,
            purpose=purpose,
            template_slug=template_slug,
            to=to,
            locale=locale,
            language=language,
            context=context,
            dedup_key=dedup_key,
            scheduled_at=scheduled_at,
            priority=priority,
        )
        log.info(
            "outbox_enqueued_via_task",
            extra={"outbox_id": outbox.id, "namespace": namespace, "purpose": purpose},
        )
        return outbox.id
    except TemplateNotFoundError as exc:  # pragma: no cover - defensive
        log.exception("template_not_found", extra={"slug": template_slug, "locale": locale})
        raise self.retry(exc=exc, countdown=60, max_retries=1)


@shared_task(bind=True, ignore_result=True)
def schedule_campaigns(self, limit: int = 5) -> None:
    now = timezone.now()
    campaigns = list(Campaign.objects.due(as_of=now)[:limit])
    for campaign in campaigns:
        updated = Campaign.objects.filter(
            pk=campaign.pk,
            status=Campaign.Status.SCHEDULED,
        ).update(status=Campaign.Status.RUNNING, updated_at=timezone.now())
        if updated:
            process_campaign.delay(campaign.pk, limit=campaign.batch_size)
    if campaigns:
        log.info("campaigns_scheduled", extra={"count": len(campaigns)})


@shared_task(bind=True, ignore_result=True)
def process_campaign(self, campaign_id: int, limit: int | None = None) -> None:
    try:
        campaign = Campaign.objects.get(pk=campaign_id)
    except Campaign.DoesNotExist:  # pragma: no cover - defensive
        log.warning("campaign_missing", extra={"campaign_id": campaign_id})
        return

    if campaign.status in (Campaign.Status.COMPLETED, Campaign.Status.PAUSED):
        return

    processed = CampaignService.enqueue_batch(campaign, limit=limit)
    if processed == 0:
        CampaignService.complete_if_done(campaign)
