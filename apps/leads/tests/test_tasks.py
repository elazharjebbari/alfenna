
from apps.leads.models import Lead
from apps.leads.constants import LeadStatus
from apps.leads.tasks import process_lead
from django.test import TestCase, override_settings
from django.core.cache import cache


class LeadsTaskTest(TestCase):
    def setUp(self):
        cache.clear()

    def test_process_validates_and_scores(self):
        lead = Lead.objects.create(
            form_kind="email_ebook",
            email="john@example.com",
            idempotency_key="k1",
            status=LeadStatus.PENDING,
        )
        process_lead(lead.id)
        lead.refresh_from_db()
        self.assertEqual(lead.status, LeadStatus.VALID)
        self.assertGreaterEqual(lead.score, 10.0)


