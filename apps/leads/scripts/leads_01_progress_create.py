"""Test creation of lead + flow session via /api/leads/progress/ step 1."""

import uuid

from django.test import Client
from django.urls import reverse

from apps.common.runscript_harness import binary_harness
from apps.leads.constants import FormKind, LeadStatus
from apps.leads.models import Lead, LeadSubmissionLog
from apps.flowforms.models import FlowSession


@binary_harness
def run():  # pragma: no cover - executed via runscript
    client = Client()
    flow_key = "checkout_intent_flow"
    session_key = f"rs-{uuid.uuid4().hex[:12]}"

    url = reverse("leads:progress")
    payload = {
        "flow_key": flow_key,
        "session_key": session_key,
        "form_kind": FormKind.CHECKOUT_INTENT,
        "step": "step1",
        "payload": {
            "full_name": "Test Customer",
            "phone": "+212600000000",
            "product": "prod-alpha",
        },
    }

    response = client.post(url, data=payload, content_type="application/json")

    logs = [
        f"status={response.status_code}",
        f"json={getattr(response, 'json', lambda: {})() if hasattr(response, 'json') else response.content[:200]}",
    ]

    if response.status_code != 200:
        for line in logs:
            print(line)
        return {"ok": False, "logs": logs}

    lead = Lead.objects.get(id=response.json()["lead_id"])
    fs = FlowSession.objects.get(flow_key=flow_key, session_key=session_key)
    log = LeadSubmissionLog.objects.get(lead=lead, flow_key=flow_key, session_key=session_key, step="step1")

    ok = (
        lead.status == LeadStatus.PENDING
        and fs.lead_id == lead.id
        and fs.data_snapshot.get("full_name") == "Test Customer"
        and log.message == "progress:step1"
    )

    logs.extend(
        [
            f"lead.id={lead.id}",
            f"lead.status={lead.status}",
            f"fs.snapshot={fs.data_snapshot}",
            f"log.message={log.message}",
        ]
    )

    for line in logs:
        print(line)

    return {"ok": ok, "logs": logs}
