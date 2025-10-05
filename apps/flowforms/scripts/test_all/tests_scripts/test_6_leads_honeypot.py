import time
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from apps.leads.models import Lead
from ._helpers_token import make_signed_token
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    t0=time.time(); logs=[]; ok=True
    c = Client()
    url = reverse("leads:collect")

    before = Lead.objects.count()
    body = {"form_kind":"email_ebook","email":"hp@test.com","client_ts": timezone.now().isoformat(),"honeypot":"BOT"}
    body["signed_token"] = make_signed_token(body)

    r = c.post(url, data=body, content_type="application/json", **{"HTTP_X_IDEMPOTENCY_KEY":"hp-1"})
    after = Lead.objects.count()
    logs.append(f"POST honeypot → {r.status_code}, leads+{after-before}")
    if r.status_code != 202 or (after-before) != 0:
        ok=False; logs.append("❌ attendu 202 sans création")

    return {"name":"Étape 6 — Honeypot stealth", "ok":ok, "duration":round(time.time()-t0,2), "logs":logs}