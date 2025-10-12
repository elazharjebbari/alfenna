"""Campaign management services for bulk messaging."""
from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import StudentProfile

from .models import Campaign, CampaignRecipient
from .services import EmailService

log = logging.getLogger("messaging.campaigns")


class CampaignService:
    @staticmethod
    @transaction.atomic
    def build_recipients(campaign: Campaign, *, limit: int | None = None) -> int:
        """Populate CampaignRecipient rows from marketing opt-ins."""
        existing = {
            email.lower(): email
            for email in campaign.recipients.values_list("email", flat=True)
        }
        qs = (
            StudentProfile.objects.select_related("user")
            .filter(marketing_opt_in=True, user__is_active=True)
            .exclude(user__email="")
        )
        locale = campaign.locale
        created = []
        seen = set(existing.keys())
        count = 0
        for profile in qs.iterator():
            user = profile.user
            if not user:
                continue
            email = (user.email or "").strip().lower()
            if not email or email in seen:
                continue
            seen.add(email)
            created.append(
                CampaignRecipient(
                    campaign=campaign,
                    email=email,
                    user=user,
                    locale=locale,
                )
            )
            count += 1
            if limit and count >= limit:
                break
        if created:
            CampaignRecipient.objects.bulk_create(created, ignore_conflicts=True)
        return len(created)

    @staticmethod
    @transaction.atomic
    def enqueue_batch(campaign: Campaign, *, limit: int | None = None) -> int:
        """Enqueue a batch of campaign emails respecting opt-in and dry-run."""
        CampaignService.build_recipients(campaign)
        limit = limit or campaign.batch_size
        pending = list(
            campaign.recipients.filter(status=CampaignRecipient.Status.PENDING)[:limit]
        )
        now = timezone.now()
        processed = 0
        metadata = campaign.metadata if isinstance(campaign.metadata, dict) else {}
        base_context = metadata.get("context", {}) if isinstance(metadata, dict) else {}
        for recipient in pending:
            if campaign.dry_run:
                recipient.status = CampaignRecipient.Status.SUPPRESSED
                recipient.last_enqueued_at = now
                recipient.save(update_fields=["status", "last_enqueued_at", "updated_at"])
                processed += 1
                continue
            context = dict(base_context)
            context.setdefault("campaign_slug", campaign.slug)
            EmailService.compose_and_enqueue(
                namespace="marketing",
                purpose=f"campaign:{campaign.slug}",
                template_slug=campaign.template_slug,
                to=[recipient.email],
                locale=campaign.locale,
                language=campaign.locale,
                dedup_key=f"campaign:{campaign.id}:{recipient.email}",
                subject_override=campaign.subject_override or None,
                metadata={"campaign_id": campaign.id},
                context=context,
            )
            recipient.status = CampaignRecipient.Status.QUEUED
            recipient.last_enqueued_at = now
            recipient.save(update_fields=["status", "last_enqueued_at", "updated_at"])
            processed += 1
        if processed:
            log.info(
                "campaign_batch_enqueued",
                extra={"campaign_id": campaign.id, "count": processed},
            )
        return processed

    @staticmethod
    @transaction.atomic
    def complete_if_done(campaign: Campaign) -> None:
        if not campaign.recipients.filter(status=CampaignRecipient.Status.PENDING).exists():
            campaign.status = Campaign.Status.COMPLETED
            campaign.save(update_fields=["status", "updated_at"])
            log.info("campaign_completed", extra={"campaign_id": campaign.id})
