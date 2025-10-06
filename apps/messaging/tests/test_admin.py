from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.messaging.models import Campaign, CampaignRecipient, EmailTemplate, OutboxEmail
from apps.messaging.template_loader import FileSystemTemplateLoader

UserModel = get_user_model()


@override_settings(ROOT_URLCONF="alfenna.urls")
class MessagingAdminTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.admin = UserModel.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpass",
        )
        FileSystemTemplateLoader().sync()
        EmailTemplate.objects.filter(slug="marketing/promo").update(is_active=True)
        assert self.client.login(username="admin", password="adminpass")

    def _outbox(self) -> OutboxEmail:
        return OutboxEmail.objects.create(
            namespace="marketing",
            purpose="test",
            dedup_key="admin-test",
            to=["user@example.com"],
            template_slug="marketing/promo",
            template_version=1,
            rendered_subject="Subject",
            rendered_text="Text",
            rendered_html="<p>html</p>",
        )

    def test_outbox_requeue_action(self) -> None:
        outbox = self._outbox()
        outbox.status = OutboxEmail.Status.FAILED
        outbox.save(update_fields=["status"])

        url = reverse("admin:messaging_outboxemail_changelist")
        response = self.client.post(url, {
            "action": "requeue_emails",
            "_selected_action": [str(outbox.pk)],
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        outbox.refresh_from_db()
        self.assertEqual(outbox.status, OutboxEmail.Status.QUEUED)

    def test_outbox_resend_action_creates_new_row(self) -> None:
        outbox = self._outbox()
        url = reverse("admin:messaging_outboxemail_changelist")
        response = self.client.post(url, {
            "action": "resend_emails",
            "_selected_action": [str(outbox.pk)],
        })
        self.assertEqual(response.status_code, 302)
        self.assertGreater(
            OutboxEmail.objects.filter(dedup_key__startswith=f"{outbox.dedup_key}:resend:").count(),
            0,
        )

    def test_outbox_export_csv_action(self) -> None:
        outbox = self._outbox()
        url = reverse("admin:messaging_outboxemail_changelist")
        response = self.client.post(url, {
            "action": "export_emails_csv",
            "_selected_action": [str(outbox.pk)],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("outbox_emails.csv", response["Content-Disposition"])

    def test_template_preview_action(self) -> None:
        template = EmailTemplate.objects.filter(slug="marketing/promo").first()
        assert template is not None
        url = reverse("admin:messaging_emailtemplate_changelist")
        response = self.client.post(url, {
            "action": "preview_template",
            "_selected_action": [str(template.pk)],
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("Prévisualisation", response.content.decode("utf-8"))

    def test_campaign_actions(self) -> None:
        campaign = Campaign.objects.create(
            name="Promo",
            slug="promo-campaign",
            template_slug="marketing/promo",
            locale="fr",
            scheduled_at=timezone.now(),
            status=Campaign.Status.SCHEDULED,
        )
        url = reverse("admin:messaging_campaign_changelist")
        self.client.post(url, {"action": "start_campaigns", "_selected_action": [campaign.pk]})
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.Status.RUNNING)

        self.client.post(url, {"action": "pause_campaigns", "_selected_action": [campaign.pk]})
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.Status.PAUSED)

        self.client.post(url, {"action": "complete_campaigns", "_selected_action": [campaign.pk]})
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.Status.COMPLETED)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_campaign_enqueue_pending_action(self) -> None:
        campaign = Campaign.objects.create(
            name="Promo",
            slug="promo-campaign-enqueue",
            template_slug="marketing/promo",
            locale="fr",
            scheduled_at=timezone.now(),
            status=Campaign.Status.SCHEDULED,
        )
        CampaignRecipient.objects.create(campaign=campaign, email="queue@example.com")
        url = reverse("admin:messaging_campaign_changelist")
        response = self.client.post(url, {"action": "enqueue_pending", "_selected_action": [campaign.pk]})
        self.assertEqual(response.status_code, 302)
        recipient = CampaignRecipient.objects.get(campaign=campaign, email="queue@example.com")
        self.assertEqual(recipient.status, CampaignRecipient.Status.QUEUED)
        self.assertTrue(
            OutboxEmail.objects.filter(dedup_key=f"campaign:{campaign.id}:queue@example.com").exists()
        )

    def test_campaign_export_csv_action(self) -> None:
        campaign = Campaign.objects.create(
            name="Promo",
            slug="promo-export",
            template_slug="marketing/promo",
            locale="fr",
            scheduled_at=timezone.now(),
            status=Campaign.Status.SCHEDULED,
        )
        url = reverse("admin:messaging_campaign_changelist")
        response = self.client.post(url, {"action": "export_campaigns_csv", "_selected_action": [campaign.pk]})
        self.assertEqual(response.status_code, 200)
        self.assertIn("messaging_campaigns.csv", response["Content-Disposition"])

    def test_campaign_recipient_admin_actions(self) -> None:
        campaign = Campaign.objects.create(
            name="Promo",
            slug="promo-recipient",
            template_slug="marketing/promo",
            locale="fr",
            scheduled_at=timezone.now(),
            status=Campaign.Status.SCHEDULED,
        )
        recipient = CampaignRecipient.objects.create(
            campaign=campaign,
            email="test@example.com",
            status=CampaignRecipient.Status.QUEUED,
        )
        url = reverse("admin:messaging_campaignrecipient_changelist")
        self.client.post(url, {"action": "mark_pending", "_selected_action": [recipient.pk]})
        recipient.refresh_from_db()
        self.assertEqual(recipient.status, CampaignRecipient.Status.PENDING)

        self.client.post(url, {"action": "suppress_recipients", "_selected_action": [recipient.pk]})
        recipient.refresh_from_db()
        self.assertEqual(recipient.status, CampaignRecipient.Status.SUPPRESSED)

    def test_campaign_recipient_export_csv_action(self) -> None:
        campaign = Campaign.objects.create(
            name="Promo",
            slug="promo-recipient-export",
            template_slug="marketing/promo",
            locale="fr",
            scheduled_at=timezone.now(),
            status=Campaign.Status.SCHEDULED,
        )
        recipient = CampaignRecipient.objects.create(
            campaign=campaign,
            email="export@example.com",
            status=CampaignRecipient.Status.PENDING,
        )
        url = reverse("admin:messaging_campaignrecipient_changelist")
        response = self.client.post(url, {"action": "export_recipients_csv", "_selected_action": [recipient.pk]})
        self.assertEqual(response.status_code, 200)
        self.assertIn("messaging_recipients.csv", response["Content-Disposition"])
