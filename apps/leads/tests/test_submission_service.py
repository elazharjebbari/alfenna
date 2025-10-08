from django.test import TestCase
from apps.leads.models import Lead, LeadSubmissionLog
from apps.leads.constants import LeadStatus
from apps.flowforms.models import FlowSession, FlowStatus
from apps.leads.submissions import submit_lead_from_flowsession


class LeadSubmissionServiceTests(TestCase):
    def setUp(self):
        self.lead = Lead.objects.create(
            form_kind="checkout_intent",
            email="old@example.com",
            idempotency_key="idem-1",
            status=LeadStatus.PENDING,
        )
        self.fs = FlowSession.objects.create(
            flow_key="checkout_intent_flow",
            session_key="sess-1",
            lead=self.lead,
            data_snapshot={
                "email": "NEW@example.com",
                "phone": "+212600000000",
                "context.note": "hello",
                "accept_terms": True,
            },
            status=FlowStatus.ACTIVE,
        )

    def test_submit_updates_lead_and_logs(self):
        res = submit_lead_from_flowsession(self.fs)
        self.assertTrue(res.ok, res.reason)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.email, "new@example.com")  # normalisé
        self.assertEqual(self.lead.phone, "+212600000000")
        log = LeadSubmissionLog.objects.get(
            lead=self.lead,
            flow_key=self.fs.flow_key,
            session_key=self.fs.session_key,
            step="",
        )
        self.assertEqual(log.status, LeadStatus.VALID)

    def test_idempotent_by_session(self):
        submit_lead_from_flowsession(self.fs)
        submit_lead_from_flowsession(self.fs)
        log = LeadSubmissionLog.objects.get(
            lead=self.lead,
            flow_key=self.fs.flow_key,
            session_key=self.fs.session_key,
            step="",
        )
        self.assertEqual(log.attempt_count, 2)
        self.assertEqual(log.status, LeadStatus.VALID)
