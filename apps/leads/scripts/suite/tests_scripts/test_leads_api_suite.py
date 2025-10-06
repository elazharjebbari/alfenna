"""
runscript leads_api_suite

Objectif :
- Rejouer les scénarios clés de test_api en conditions réelles via le Django test client.
- Variables codées en dur pour reproductibilité.

Lancer :
  python manage.py runscript leads_api_suite
"""

import time
import hmac
import json
import hashlib

from django.test import Client
from django.urls import reverse
from django.utils import timezone
from django.conf import settings

from apps.leads.models import Lead
from apps.leads.constants import FormKind
from apps.common.runscript_harness import binary_harness


# =========================
# Configuration "en dur"
# =========================
URL_NAME = "leads:collect"

EMAIL_OK = "foo@example.com"
EMAIL_HP = "honeypot@example.com"
IDEMPOTENCY_OK = "api-ebook-1"
IDEMPOTENCY_HP = "api-hp-1"
# Pas d'idempotency pour le scénario "missing idempotency"

# Helper : construit le token signé attendu par l'API (HMAC(ts.md5(bodySansToken)))
def make_signed_token(body: dict, secret: str | None = None, ts: int | None = None) -> str:
    secret = secret or getattr(settings, "LEADS_SIGNING_SECRET", settings.SECRET_KEY)
    ts = ts or int(time.time())
    body_wo_token = dict(body)
    body_wo_token.pop("signed_token", None)
    msg = hashlib.md5(json.dumps(body_wo_token, sort_keys=True).encode("utf-8")).hexdigest()
    mac = hmac.new(secret.encode("utf-8"), f"{ts}.{msg}".encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{ts}.{mac}"

def pretty(resp):
    try:
        return json.loads(resp.content.decode("utf-8"))
    except Exception:
        return resp.content[:300].decode(errors="ignore")

@binary_harness
def run():
    client = Client()
    url = reverse(URL_NAME)

    print("\n== Nettoyage minimal (emails utilisés dans ce script)")
    Lead.objects.filter(email__in=[EMAIL_OK, EMAIL_HP]).delete()

    # --- Scénario 1 : email_ebook OK ---
    print("\n[1] email_ebook OK (202 + création Lead + file Celery)")
    body_ok = {
        "form_kind": FormKind.EMAIL_EBOOK,
        "email": EMAIL_OK,
        "client_ts": timezone.now().isoformat(),
        "honeypot": "",
    }
    body_ok["signed_token"] = make_signed_token(body_ok)

    before = Lead.objects.count()
    r1 = client.post(
        url,
        data=body_ok,
        content_type="application/json",
        **{"HTTP_X_IDEMPOTENCY_KEY": IDEMPOTENCY_OK},
    )
    after = Lead.objects.count()

    print("Status:", r1.status_code)
    print("Body:", pretty(r1))
    print("Leads +", after - before)
    if r1.status_code == 202 and (after - before) == 1:
        lead = Lead.objects.order_by("-id").first()
        print("Lead créé => id:", lead.id, "kind:", lead.form_kind, "email:", lead.email)
    else:
        print("ATTENTION: échec scénario 1")

    # --- Scénario 2 : Missing Idempotency ---
    print("\n[2] Missing X-Idempotency-Key (400)")
    body_missing = {
        "form_kind": FormKind.EMAIL_EBOOK,
        "email": "missing-idem@example.com",
        "client_ts": timezone.now().isoformat(),
        "honeypot": "",
    }
    body_missing["signed_token"] = make_signed_token(body_missing)

    r2 = client.post(url, data=body_missing, content_type="application/json")
    print("Status:", r2.status_code)
    print("Body:", pretty(r2))
    if r2.status_code != 400:
        print("ATTENTION: ce scénario devait renvoyer 400")

    # --- Scénario 3 : Honeypot reject (202 stealth, sans création) ---
    print("\n[3] Honeypot rempli (202, pas de création)")
    before_hp = Lead.objects.count()
    body_hp = {
        "form_kind": FormKind.EMAIL_EBOOK,
        "email": EMAIL_HP,
        "client_ts": timezone.now().isoformat(),
        "honeypot": "bot",   # => déclenche rejet
    }
    body_hp["signed_token"] = make_signed_token(body_hp)

    r3 = client.post(
        url,
        data=body_hp,
        content_type="application/json",
        **{"HTTP_X_IDEMPOTENCY_KEY": IDEMPOTENCY_HP},
    )
    after_hp = Lead.objects.count()

    print("Status:", r3.status_code)
    print("Body:", pretty(r3))
    print("Leads +", after_hp - before_hp)
    if r3.status_code == 202 and (after_hp - before_hp) == 0:
        print("OK: rejet silencieux (stealth) confirmé")
    else:
        print("ATTENTION: ce scénario devait renvoyer 202 sans créer de lead")

    print("\n== FIN SUITE API ==")
