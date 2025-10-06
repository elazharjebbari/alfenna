from __future__ import annotations

from django.utils import timezone

from apps.accounts.models import StudentProfile
from django.contrib.auth import get_user_model

from apps.messaging.campaigns import CampaignService
from apps.messaging.models import Campaign, CampaignRecipient, OutboxEmail


def run():
    User = get_user_model()
    user, _ = User.objects.get_or_create(username="campaign-script", defaults={"email": "campaign@example.com"})
    user.email = user.email or "campaign@example.com"
    user.is_active = True
    user.save(update_fields=["email", "is_active"])
    profile, _ = StudentProfile.objects.get_or_create(user=user)
    StudentProfile.objects.filter(pk=profile.pk).update(marketing_opt_in=True, marketing_opt_out_at=None)

    campaign, _ = Campaign.objects.get_or_create(
        slug="diagnostic-campaign",
        defaults={
            "name": "Diagnostic Campaign",
            "template_slug": "marketing/promo",
            "locale": "fr",
            "scheduled_at": timezone.now(),
            "status": Campaign.Status.SCHEDULED,
            "dry_run": True,
        },
    )

    CampaignService.build_recipients(campaign)
    CampaignService.enqueue_batch(campaign, limit=5)

    queued = campaign.recipients.filter(status=CampaignRecipient.Status.QUEUED).count()
    suppressed = campaign.recipients.filter(status=CampaignRecipient.Status.SUPPRESSED).count()
    outbox = OutboxEmail.objects.filter(dedup_key__startswith=f"campaign:{campaign.id}:").count()

    return {
        "ok": suppressed >= 1,
        "name": "test_campaign",
        "duration": 0.0,
        "logs": [f"queued={queued}", f"suppressed={suppressed}", f"outbox={outbox}"],
    }
