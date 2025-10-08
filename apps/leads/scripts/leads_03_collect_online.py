"""Happy-path collect flow for checkout_intent (progress + collect + process)."""

import uuid

from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.common.runscript_harness import binary_harness
from apps.leads.constants import FormKind, LeadStatus
from apps.leads.models import Lead, LeadSubmissionLog
from apps.leads.tasks import process_lead


@binary_harness
def run():  # pragma: no cover - executed via runscript
    client = Client()
    flow_key = "checkout_intent_flow"
    session_key = f"rs-{uuid.uuid4().hex[:10]}"
    idem_key = f"idem-{uuid.uuid4().hex[:12]}"

    progress_url = reverse("leads:progress")
    collect_url = reverse("leads:collect")

    Lead.objects.filter(phone="+212650000000").delete()

    step1_body = {
        "flow_key": flow_key,
        "session_key": session_key,
        "form_kind": FormKind.CHECKOUT_INTENT,
        "step": "step1",
        "payload": {
            "full_name": "Progress User",
            "phone": "+212650000000",
            "product": "pack-alpha",
            "wa_optin": True,
        },
    }
    step2_body = {
        "flow_key": flow_key,
        "session_key": session_key,
        "form_kind": FormKind.CHECKOUT_INTENT,
        "step": "step2",
        "payload": {
            "offer_key": "pack-duo",
            "quantity": 2,
            "address_raw": "123 Rue Exemple, Casa",
            "bump_optin": False,
            "promotion_selected": "",
            "payment_method": "cod",
        },
    }

    r1 = client.post(progress_url, data=step1_body, content_type="application/json")
    r2 = client.post(progress_url, data=step2_body, content_type="application/json")

    collect_body = {
        "form_kind": FormKind.CHECKOUT_INTENT,
        "full_name": "Progress User",
        "phone": "+212650000000",
        "email": "progress@example.com",
        "product": "pack-alpha",
        "offer_key": "pack-duo",
        "quantity": 2,
        "address_raw": "123 Rue Exemple, Casa",
        "payment_method": "cod",
        "course_slug": "pack-alpha",
        "currency": "MAD",
        "accept_terms": True,
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

    logs = [
        f"progress step1={r1.status_code}",
        f"progress step2={r2.status_code}",
        f"collect status={collect_resp.status_code}",
    ]

    if collect_resp.status_code != 202:
        for line in logs:
            print(line)
        return {"ok": False, "logs": logs}

    lead = Lead.objects.get(phone="+212650000000")
    process_lead(lead.id)
    lead.refresh_from_db()

    log_collect = LeadSubmissionLog.objects.filter(
        lead=lead, flow_key=flow_key, session_key=session_key, step="collect"
    ).first()

    ok = (
        lead.status == LeadStatus.VALID
        and lead.idempotency_key == idem_key
        and log_collect is not None
    )

    logs.extend([
        f"lead.id={lead.id}",
        f"lead.status={lead.status}",
        f"lead.idem={lead.idempotency_key}",
        f"collect_log_exists={bool(log_collect)}",
    ])

    for line in logs:
        print(line)

    return {"ok": ok, "logs": logs}
