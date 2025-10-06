from __future__ import annotations
from django.test import TestCase, RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware
from django.utils import timezone

from apps.flowforms.engine.storage import get_or_create_session, persist_step, FlowContext
from apps.flowforms.models import FlowSession, FlowStatus
from apps.leads.models import Lead
from apps.leads.constants import LeadStatus

def add_session(request):
    """Attache une session persistante à une requête (RequestFactory)."""
    middleware = SessionMiddleware(lambda r: None)
    middleware.process_request(request)
    request.session.save()
    return request

class FlowFormsStorageTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.ctx = FlowContext(flow_key="checkout_flow", form_kind="checkout_intent")

    def test_flowsession_created_and_updated(self):
        req = add_session(self.factory.get("/flows/checkout_flow/"))
        fs = get_or_create_session(req, self.ctx)
        self.assertIsInstance(fs, FlowSession)
        self.assertEqual(fs.flow_key, "checkout_flow")
        self.assertEqual(fs.status, FlowStatus.ACTIVE)

        # Persist une première step
        lead, fs = persist_step(
            flowsession=fs,
            ctx=self.ctx,
            step_key="step1",
            cleaned_data={"email": "john@example.com", "course_slug": "python-pro"},
        )
        self.assertIsNotNone(lead.id)
        self.assertEqual(fs.current_step, "step1")
        self.assertEqual(fs.data_snapshot.get("email"), "john@example.com")

        # Persist une seconde step (merge snapshot)
        lead2, fs2 = persist_step(
            flowsession=fs,
            ctx=self.ctx,
            step_key="step2",
            cleaned_data={"phone": "+212600000000"},
        )
        self.assertEqual(lead.id, lead2.id)
        self.assertEqual(fs2.data_snapshot.get("email"), "john@example.com")
        self.assertEqual(fs2.data_snapshot.get("phone"), "+212600000000")
        self.assertEqual(fs2.current_step, "step2")

    def test_merge_with_existing_lead_by_lookup(self):
        # Lead déjà existant (même form_kind + email)
        existing = Lead.objects.create(
            form_kind="checkout_intent",
            email="merge@example.com",
            idempotency_key="preexisting-1",
            status=LeadStatus.PENDING,
        )
        req = add_session(self.factory.get("/flows/checkout_flow/"))
        fs = get_or_create_session(req, self.ctx)
        # Step avec même email => doit attacher ce lead
        lead, fs = persist_step(
            flowsession=fs,
            ctx=self.ctx,
            step_key="step1",
            cleaned_data={"email": "merge@example.com"},
        )
        self.assertEqual(lead.id, existing.id)
        self.assertEqual(fs.lead_id, existing.id)

    def test_parallel_flows_do_not_conflict(self):
        req = add_session(self.factory.get("/"))

        # Flow A
        ctx_a = FlowContext(flow_key="flow_a", form_kind="contact_full")
        fs_a = get_or_create_session(req, ctx_a)
        lead_a, fs_a = persist_step(flowsession=fs_a, ctx=ctx_a, step_key="a1", cleaned_data={"email": "a@ex.com"})

        # Flow B (même session_key mais flow_key différent)
        ctx_b = FlowContext(flow_key="flow_b", form_kind="email_ebook")
        fs_b = get_or_create_session(req, ctx_b)
        lead_b, fs_b = persist_step(flowsession=fs_b, ctx=ctx_b, step_key="b1", cleaned_data={"email": "b@ex.com"})

        self.assertNotEqual(fs_a.flow_key, fs_b.flow_key)
        self.assertNotEqual(fs_a.id, fs_b.id)
        self.assertNotEqual(lead_a.id, lead_b.id)
        self.assertEqual(fs_a.data_snapshot.get("email"), "a@ex.com")
        self.assertEqual(fs_b.data_snapshot.get("email"), "b@ex.com")