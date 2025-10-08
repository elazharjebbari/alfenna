"""Progress endpoint should reject malformed payloads without side effects."""

from django.test import Client
from django.urls import reverse

from apps.common.runscript_harness import binary_harness
from apps.leads.models import LeadSubmissionLog


@binary_harness
def run():  # pragma: no cover - executed via runscript
    client = Client()
    url = reverse("leads:progress")

    before = LeadSubmissionLog.objects.count()
    resp = client.post(url, data={"flow_key": ""}, content_type="application/json")
    after = LeadSubmissionLog.objects.count()

    print(f"status={resp.status_code} logs_before={before} logs_after={after}")

    return {"ok": resp.status_code == 400 and before == after, "logs": [f"status={resp.status_code}"]}
