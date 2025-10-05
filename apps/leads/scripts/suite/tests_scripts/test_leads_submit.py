"""
runscript leads_submit
"""

import time, json, hmac, hashlib
from django.utils import timezone
from django.test import Client
from django.conf import settings
from django.urls import reverse
from apps.common.runscript_harness import binary_harness

def make_token(body: dict):
    ts = int(time.time())
    msg = hashlib.md5(json.dumps({k:v for k,v in body.items() if k!="signed_token"}, sort_keys=True).encode()).hexdigest()
    mac = hmac.new(getattr(settings, "LEADS_SIGNING_SECRET", settings.SECRET_KEY).encode(), f"{ts}.{msg}".encode(), hashlib.sha256).hexdigest()
    return f"{ts}.{mac}"

@binary_harness
def run():
    c = Client()
    url = reverse("leads:collect")

    body = {
        "form_kind": "checkout_intent",
        "course_slug": "python-pro",
        "currency": "EUR",
        "email": "test@example.com",
        "accept_terms": True,
        "client_ts": timezone.now().isoformat(),
        "honeypot": "",
    }
    body["signed_token"] = make_token(body)

    r = c.post(url, data=body, content_type="application/json", **{"HTTP_X_IDEMPOTENCY_KEY": "demo-1234"})
    print("Status:", r.status_code, r.content)