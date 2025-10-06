"""
runscript leads_rate_limit
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

    for i in range(0, 15):
        body = {
            "form_kind": "email_ebook",
            "email": "ratelimit@example.com",
            "client_ts": timezone.now().isoformat(),
            "honeypot": "",
        }
        body["signed_token"] = make_token(body)
        r = c.post(url, data=body, content_type="application/json", **{"HTTP_X_IDEMPOTENCY_KEY": f"idem-{i}"})
        print(i, "=>", r.status_code)
        time.sleep(0.2)