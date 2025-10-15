from __future__ import annotations

import uuid

from django.test import Client, TestCase
from django.urls import reverse

from apps.flowforms.models import FlowSession
from apps.leads.constants import FormKind, LeadStatus
from apps.leads.models import LeadSubmissionLog, Lead


class ProgressStepperTests(TestCase):
    def test_stepper_progress_flow_sends_each_step(self) -> None:
        client = Client()
        flow_key = "checkout_intent_flow"
        session_key = f"ts-{uuid.uuid4().hex[:12]}"

        progress_url = reverse("leads:progress")
        collect_url = reverse("leads:collect")

        step1_payload = {
            "flow_key": flow_key,
            "session_key": session_key,
            "form_kind": FormKind.CHECKOUT_INTENT,
            "step": "step1",
            "payload": {
                "full_name": "Stepper Demo",
                "phone": "+212633334444",
                "product": "pack-progress",
                "wa_optin": True,
            },
        }

        step2_payload = {
            "flow_key": flow_key,
            "session_key": session_key,
            "form_kind": FormKind.CHECKOUT_INTENT,
            "step": "step2",
            "payload": {
                "offer_key": "pack-duo",
                "quantity": 2,
                "address_raw": "10 rue Test, Rabat",
                "payment_method": "cod",
                "bump_optin": False,
                "promotion_selected": "",
            },
        }

        resp_step1 = client.post(progress_url, data=step1_payload, content_type="application/json")
        resp_step2 = client.post(progress_url, data=step2_payload, content_type="application/json")

        self.assertEqual(resp_step1.status_code, 200)
        self.assertEqual(resp_step2.status_code, 200)

        fs = FlowSession.objects.get(flow_key=flow_key, session_key=session_key)
        self.assertEqual(fs.data_snapshot.get("full_name"), "Stepper Demo")
        self.assertEqual(fs.data_snapshot.get("offer_key"), "pack-duo")

        logs = LeadSubmissionLog.objects.filter(flow_key=flow_key, session_key=session_key).order_by("step")
        self.assertEqual(logs.count(), 2)
        self.assertEqual({log.step for log in logs}, {"step1", "step2"})

        idem_key = f"idem-{uuid.uuid4().hex[:8]}"
        collect_payload = {
            "form_kind": FormKind.CHECKOUT_INTENT,
            "full_name": "Stepper Demo",
            "phone": "+212633334444",
            "email": "stepper@example.com",
            "product": "pack-progress",
            "offer_key": "pack-duo",
            "quantity": 2,
            "address_raw": "10 rue Test, Rabat",
            "payment_method": "cod",
            "course_slug": "pack-progress",
            "currency": "MAD",
            "accept_terms": True,
            "ff_flow_key": flow_key,
            "ff_session_key": session_key,
        }

        collect_resp = client.post(
            collect_url,
            data=collect_payload,
            content_type="application/json",
            **{"HTTP_X_IDEMPOTENCY_KEY": idem_key},
        )

        self.assertEqual(collect_resp.status_code, 202)

        lead = Lead.objects.get(phone="+212633334444")
        self.assertEqual(lead.idempotency_key, idem_key)
        self.assertEqual(lead.status, LeadStatus.VALID)

        collect_log = LeadSubmissionLog.objects.get(
            lead=lead,
            flow_key=flow_key,
            session_key=session_key,
            step="collect",
        )
        self.assertIn(collect_log.status, {LeadStatus.PENDING, LeadStatus.VALID})
