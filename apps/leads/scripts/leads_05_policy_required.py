"""Ensure business-required fields reject during async processing."""

import uuid

from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.common.runscript_harness import binary_harness
from apps.leads.constants import FormKind, LeadStatus
from apps.leads.models import Lead
from apps.leads.tasks import process_lead


@binary_harness
def run():  # pragma: no cover - executed via runscript
    client = Client()
    flow_key = "checkout_intent_flow"
    session_key = f"rs-{uuid.uuid4().hex[:10]}"
    idem_key = f"idem-{uuid.uuid4().hex[:12]}"

    progress_url = reverse("leads:progress")
    collect_url = reverse("leads:collect")

    Lead.objects.filter(phone="+212677777777").delete()

    client.post(
        progress_url,
        data={
            "flow_key": flow_key,
            "session_key": session_key,
            "form_kind": FormKind.CHECKOUT_INTENT,
            "step": "step1",
            "payload": {"full_name": "Policy Lead"},
        },
        content_type="application/json",
    )

    collect_body = {
        "form_kind": FormKind.CHECKOUT_INTENT,
        "full_name": "Policy Lead",
        "phone": "+212677777777",
        "course_slug": "policy-pack",
        "currency": "MAD",
        "accept_terms": False,  # deliberately false to trigger rejection in process_lead
        "ff_flow_key": flow_key,
        "ff_session_key": session_key,
        "client_ts": timezone.now().isoformat(),
    }

    collect_resp = client.post(
        collect_url,
        data=collect_body,
        content_type="application/json",
        **{"HTTP_X_IDEMPOTENCY_KEY": idem_key},
    )

    lead = Lead.objects.order_by("-id").first()
    ok_collect = collect_resp.status_code == 202 and lead is not None

    if lead:
        process_lead(lead.id)
        lead.refresh_from_db()

    ok = ok_collect and lead and lead.status == LeadStatus.REJECTED

    logs = [
        f"collect status={collect_resp.status_code}",
        f"lead.status={lead.status if lead else 'N/A'}",
    ]

    for line in logs:
        print(line)

    return {"ok": ok, "logs": logs}
