"""Validate idempotent progress logging and snapshot merge."""

import uuid

from django.test import Client
from django.urls import reverse

from apps.common.runscript_harness import binary_harness
from apps.leads.constants import FormKind
from apps.leads.models import LeadSubmissionLog
from apps.flowforms.models import FlowSession


@binary_harness
def run():  # pragma: no cover - executed via runscript
    client = Client()
    flow_key = "checkout_intent_flow"
    session_key = f"rs-{uuid.uuid4().hex[:12]}"

    url = reverse("leads:progress")

    step1 = {
        "flow_key": flow_key,
        "session_key": session_key,
        "form_kind": FormKind.CHECKOUT_INTENT,
        "step": "step1",
        "payload": {
            "full_name": "Alice",
            "phone": "+212611112222",
            "product": "prod-1",
        },
    }

    step2 = {
        "flow_key": flow_key,
        "session_key": session_key,
        "form_kind": FormKind.CHECKOUT_INTENT,
        "step": "step2",
        "payload": {
            "offer_key": "pack_duo",
            "quantity": 2,
            "address_raw": "12 rue Exemple, Casablanca",
        },
    }

    r1 = client.post(url, data=step1, content_type="application/json")
    r1b = client.post(url, data=step1, content_type="application/json")
    r2 = client.post(url, data=step2, content_type="application/json")

    fs = FlowSession.objects.get(flow_key=flow_key, session_key=session_key)
    logs = list(
        LeadSubmissionLog.objects.filter(flow_key=flow_key, session_key=session_key).order_by("step")
    )

    ok = (
        r1.status_code == 200
        and r1b.status_code == 200
        and r2.status_code == 200
        and len(logs) == 2
        and fs.data_snapshot.get("quantity") == 2
        and fs.data_snapshot.get("offer_key") == "pack_duo"
        and fs.data_snapshot.get("full_name") == "Alice"
    )

    output = [
        f"r1={r1.status_code}",
        f"r1b={r1b.status_code}",
        f"r2={r2.status_code}",
        f"logs={[(log.step, log.message) for log in logs]}",
        f"snapshot={fs.data_snapshot}",
    ]

    for line in output:
        print(line)

    return {"ok": ok, "logs": output}
