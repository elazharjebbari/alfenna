from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
import json, time, hmac, hashlib
from django.conf import settings
from apps.leads.models import Lead

def sign(body):
    ts = int(time.time())
    msg = hashlib.md5(json.dumps({k:v for k,v in body.items() if k!="signed_token"}, sort_keys=True).encode()).hexdigest()
    mac = hmac.new(getattr(settings, "LEADS_SIGNING_SECRET", settings.SECRET_KEY).encode(), f"{ts}.{msg}".encode(), hashlib.sha256).hexdigest()
    return f"{ts}.{mac}"

class ProductLeadOptionalTests(TestCase):
    def setUp(self):
        self.url = reverse("leads:collect")

    def test_ok_without_email_and_address(self):
        body = {
            "form_kind": "product_lead",
            "full_name": "Client Test",
            "phone": "+212612345678",
            "honeypot": "",
            "client_ts": timezone.now().isoformat(),
        }
        body["signed_token"] = sign(body)
        r = self.client.post(self.url, data=body, content_type="application/json", HTTP_X_IDEMPOTENCY_KEY="key-1")
        self.assertEqual(r.status_code, 202, r.content)

    def test_reject_without_phone(self):
        body = {"form_kind": "product_lead", "full_name": "X", "honeypot": ""}
        body["signed_token"] = sign(body)
        r = self.client.post(self.url, data=body, content_type="application/json", HTTP_X_IDEMPOTENCY_KEY="key-2")
        self.assertNotEqual(r.status_code, 202)  # phone reste requis
