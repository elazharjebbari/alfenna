from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import StudentProfile
from apps.messaging.campaigns import CampaignService
from apps.messaging.models import Campaign, CampaignRecipient, OutboxEmail
from apps.messaging.template_loader import FileSystemTemplateLoader

UserModel = get_user_model()


class CampaignServiceTests(TestCase):
    def setUp(self) -> None:
        FileSystemTemplateLoader().sync()
        self.campaign = Campaign.objects.create(
            name="Promo",
            slug="promo-oct",
            template_slug="marketing/promo",
            locale="fr",
            scheduled_at=timezone.now(),
            status=Campaign.Status.SCHEDULED,
        )
        self.opt_in = UserModel.objects.create_user(username="optin", email="optin@example.com", password="x")
        profile_in, _ = StudentProfile.objects.get_or_create(user=self.opt_in)
        StudentProfile.objects.filter(pk=profile_in.pk).update(marketing_opt_in=True, marketing_opt_out_at=None)
        self.opt_out = UserModel.objects.create_user(username="optout", email="optout@example.com", password="x")
        profile_out, _ = StudentProfile.objects.get_or_create(user=self.opt_out)
        StudentProfile.objects.filter(pk=profile_out.pk).update(marketing_opt_in=False)

    def test_build_recipients_only_includes_opt_in(self) -> None:
        created = CampaignService.build_recipients(self.campaign)
        self.assertEqual(created, 1)
        emails = list(self.campaign.recipients.values_list("email", flat=True))
        self.assertEqual(emails, ["optin@example.com"])

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_enqueue_batch_creates_outbox_entries(self) -> None:
        CampaignService.build_recipients(self.campaign)
        count = CampaignService.enqueue_batch(self.campaign, limit=10)
        self.assertEqual(count, 1)
        recipient = CampaignRecipient.objects.get(campaign=self.campaign, email="optin@example.com")
        self.assertEqual(recipient.status, CampaignRecipient.Status.QUEUED)
        outbox = OutboxEmail.objects.get(dedup_key=f"campaign:{self.campaign.id}:optin@example.com")
        self.assertEqual(outbox.namespace, "marketing")

    def test_dry_run_marks_suppressed(self) -> None:
        self.campaign.dry_run = True
        self.campaign.save(update_fields=["dry_run"])
        CampaignService.build_recipients(self.campaign)
        count = CampaignService.enqueue_batch(self.campaign)
        self.assertEqual(count, 1)
        recipient = CampaignRecipient.objects.get(campaign=self.campaign, email="optin@example.com")
        self.assertEqual(recipient.status, CampaignRecipient.Status.SUPPRESSED)
        self.assertEqual(
            OutboxEmail.objects.filter(dedup_key__startswith=f"campaign:{self.campaign.id}:").count(),
            0,
        )
