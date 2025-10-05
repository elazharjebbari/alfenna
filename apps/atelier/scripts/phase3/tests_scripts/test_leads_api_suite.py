"""
Soumet 3 leads différents à l'API /api/leads/collect/ et vérifie 202.
Exécution: python manage.py runscript leads_api_suite
"""
import time, json, hmac, hashlib
from django.utils import timezone
from django.test import Client
from django.conf import settings
from django.urls import reverse
from apps.common.runscript_harness import binary_harness

def _make_token(body: dict):
    ts = int(time.time())
    # hash stable du body sans signed_token
    msg = hashlib.md5(json.dumps({k:v for k,v in body.items() if k!="signed_token"}, sort_keys=True).encode()).hexdigest()
    mac = hmac.new(getattr(settings, "LEADS_SIGNING_SECRET", settings.SECRET_KEY).encode(), f"{ts}.{msg}".encode(), hashlib.sha256).hexdigest()
    return f"{ts}.{mac}"

def _post(client, body: dict, idem: str):
    body["signed_token"] = _make_token(body)
    url = reverse("leads:collect")
    resp = client.post(url, data=body, content_type="application/json", **{"HTTP_X_IDEMPOTENCY_KEY": idem})
    print(f"POST {body['form_kind']} → {resp.status_code} {resp.content[:120]}")
    assert resp.status_code in (202, 200), f"Status inattendu: {resp.status_code}"

@binary_harness
def run():
    print("=== leads_api_suite ===")
    c = Client()

    # 1) email_ebook simple
    _post(c, {
        "form_kind": "email_ebook",
        "email": "ebook@example.com",
        "first_name": "Eve",
        "newsletter_optin": True,
        "client_ts": timezone.now().isoformat(),
        "honeypot": "",
    }, idem="ebook-1")

    # 2) contact_full minimal
    _post(c, {
        "form_kind": "contact_full",
        "email": "contact@example.com",
        "message": "Je souhaite plus d'infos.",
        "client_ts": timezone.now().isoformat(),
        "honeypot": "",
    }, idem="contact-1")

    # 3) checkout_intent
    _post(c, {
        "form_kind": "checkout_intent",
        "course_slug": "initiation-bougies-presentiel",  # slug réel de ton course
        "currency": "EUR",
        "email": "buyer@example.com",
        "accept_terms": True,
        "client_ts": timezone.now().isoformat(),
        "honeypot": "",
    }, idem="checkout-1")

    print("=> Leads API suite OK ✅")