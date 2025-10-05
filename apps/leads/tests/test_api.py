from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
import time, hmac, hashlib, json
from django.conf import settings
from apps.leads.models import Lead
from apps.leads.constants import FormKind
from django.core.cache import cache

def make_token(body: dict, age=0):
    ts = int(time.time() - age)
    msg = hashlib.md5(json.dumps({k:v for k,v in body.items() if k!="signed_token"}, sort_keys=True).encode()).hexdigest()
    mac = hmac.new(getattr(settings, "LEADS_SIGNING_SECRET", settings.SECRET_KEY).encode(), f"{ts}.{msg}".encode(), hashlib.sha256).hexdigest()
    return f"{ts}.{mac}"

class LeadsAPITest(TestCase):
    def setUp(self):
        self.url = reverse("leads:collect")
        cache.clear()
    def test_email_ebook_ok(self):
        body = {
            "form_kind": "email_ebook",
            "email": "foo@example.com",
            "client_ts": timezone.now().isoformat(),
            "honeypot": "",
            "signed_token": "will_be_set",
        }
        body["signed_token"] = make_token(body)
        resp = self.client.post(self.url, data=body, content_type="application/json", HTTP_X_IDEMPOTENCY_KEY="test1")
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(Lead.objects.count(), 1)
        lead = Lead.objects.first()
        self.assertEqual(lead.form_kind, FormKind.EMAIL_EBOOK)

    def test_missing_idempotency(self):
        body = {"form_kind": "email_ebook", "email": "a@b.com", "signed_token": "x", "honeypot": ""}
        body["signed_token"] = make_token(body)
        resp = self.client.post(self.url, data=body, content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_honeypot_reject(self):
        body = {"form_kind": "email_ebook", "email": "x@y.com", "honeypot": "bot", "signed_token": "x"}
        body["signed_token"] = make_token(body)
        resp = self.client.post(self.url, data=body, content_type="application/json", HTTP_X_IDEMPOTENCY_KEY="hp1")
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(Lead.objects.count(), 0)  # on ne crée pas si honeypot ? (ici on renvoie 202 sans créer)



