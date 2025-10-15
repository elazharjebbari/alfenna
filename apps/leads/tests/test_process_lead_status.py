from uuid import uuid4

from django.test import TestCase

from apps.leads.constants import FormKind, LeadStatus
from apps.leads.models import Lead
from apps.leads.tasks import process_lead


class ProcessLeadStatusTests(TestCase):

    def _make_lead(self, **overrides):
        defaults = {
            "form_kind": FormKind.CHECKOUT_INTENT,
            "status": LeadStatus.PENDING,
            "phone": "0612345678",
            "pack_slug": "pack-duo",
            "payment_mode": "online",
            "accept_terms": True,
            "context": {"complementary_slugs": ["bougie-massage"]},
            "idempotency_key": overrides.pop("idempotency_key", uuid4().hex),
        }
        defaults.update(overrides)
        return Lead.objects.create(**defaults)

    def test_process_lead_marks_valid_when_hard_required_present(self):
        lead = self._make_lead()

        process_lead.run(lead.id)

        lead.refresh_from_db()
        self.assertEqual(lead.status, LeadStatus.VALID)
        self.assertNotEqual(lead.score, 0.0)

    def test_process_lead_rejects_when_hard_required_missing(self):
        lead = self._make_lead(phone="", idempotency_key=uuid4().hex)

        process_lead.run(lead.id)

        lead.refresh_from_db()
        self.assertEqual(lead.status, LeadStatus.REJECTED)
        self.assertEqual(lead.reject_reason, "INVALID")
