from __future__ import annotations

from django.test import TestCase
from django.utils import timezone

from apps.messaging.models import Campaign, CampaignRecipient, OutboxEmail
from apps.messaging.scripts import diagnostics


class DiagnosticsScriptTests(TestCase):
    def setUp(self) -> None:
        now = timezone.now()
        OutboxEmail.objects.create(
            namespace="accounts",
            purpose="reset",
            dedup_key="diag-test",
            to=["user@example.com"],
            template_slug="accounts/reset",
            template_version=1,
            rendered_subject="subject",
            rendered_text="text",
            rendered_html="<p>html</p>",
            status=OutboxEmail.Status.FAILED,
            scheduled_at=now,
            last_error_at=now,
            last_error_message="SMTP 500",
        )
        campaign = Campaign.objects.create(
            name="Diag",
            slug="diag-campaign",
            template_slug="marketing/promo",
            locale="fr",
            scheduled_at=now,
            status=Campaign.Status.RUNNING,
        )
        CampaignRecipient.objects.create(
            campaign=campaign,
            email="diag@example.com",
            status=CampaignRecipient.Status.PENDING,
        )

    def test_run_returns_logs(self) -> None:
        result = diagnostics.run()
        self.assertTrue(result["ok"])
        logs = result.get("logs", [])
        joined = "\n".join(logs)
        self.assertIn("Outbox (24h)", joined)
        self.assertIn("Top erreurs SMTP", joined)
        self.assertIn("Campagnes actives", joined)
