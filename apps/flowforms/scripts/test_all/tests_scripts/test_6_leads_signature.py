import time
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from ._helpers_token import make_signed_token
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    t0=time.time(); logs=[]; ok=True
    c = Client()
    url = reverse("leads:collect")

    # sans token → 400
    body_bad = {"form_kind":"email_ebook","email":"sig@test.com","client_ts": timezone.now().isoformat(),"honeypot":""}
    r_bad = c.post(url, data=body_bad, content_type="application/json", **{"HTTP_X_IDEMPOTENCY_KEY":"sig-0"})
    logs.append(f"Sans signed_token → {r_bad.status_code}")
    if r_bad.status_code != 400: ok=False; logs.append("❌ attendu 400 sans token")

    # bon token → 202
    body_ok = dict(body_bad)
    body_ok["signed_token"] = make_signed_token(body_ok)
    r_ok = c.post(url, data=body_ok, content_type="application/json", **{"HTTP_X_IDEMPOTENCY_KEY":"sig-1"})
    logs.append(f"Avec signed_token → {r_ok.status_code}")
    if r_ok.status_code not in (200,202): ok=False; logs.append("❌ attendu 200/202 avec token")

    return {"name":"Étape 6 — Signature HMAC", "ok":ok, "duration":round(time.time()-t0,2), "logs":logs}