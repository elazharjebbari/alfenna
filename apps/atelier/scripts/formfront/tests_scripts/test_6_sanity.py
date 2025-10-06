import time, uuid, json
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from django.core.cache import cache
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    t0 = time.time()
    logs = []
    ok = True

    # Évite les faux "duplicate" / idempotency récupérés d'un run précédent
    cache.clear()

    c = Client()
    try:
        collect_url = reverse("leads:collect")
        sign_url = reverse("leads:sign")
    except Exception as e:
        return {
            "name": "Étape 6 — Sanity collect",
            "ok": False,
            "duration": round(time.time() - t0, 2),
            "logs": [f"Reverse error: {e}"],
        }

    uniq = uuid.uuid4().hex[:8]
    body = {
        "form_kind": "email_ebook",
        "email": f"sanity+{uniq}@example.com",
        "client_ts": timezone.now().isoformat(),
        "honeypot": "",
    }

    # 1) Obtenir un token signé côté serveur
    r_sign = c.post(sign_url, data={"payload": body}, content_type="application/json")
    try:
        token = (r_sign.json() or {}).get("signed_token")
    except Exception:
        token = None

    logs.append(f"Sign: {r_sign.status_code} token_present={bool(token)}")
    if r_sign.status_code != 200 or not token:
        ok = False
        logs.append("Echec signature; abandon du test.")
        return {
            "name": "Étape 6 — Sanity collect",
            "ok": ok,
            "duration": round(time.time() - t0, 2),
            "logs": logs,
        }

    # 2) Soumission collect (idempotency unique)
    send = dict(body)
    send["signed_token"] = token
    idem = f"sanity-{uniq}"

    r = c.post(collect_url, data=json.dumps(send, ensure_ascii=False, separators=(",", ":")),
               content_type="application/json",
               **{"HTTP_X_IDEMPOTENCY_KEY": idem})

    logs.append(f"Collect: {r.status_code} {r.content[:200].decode(errors='ignore')}")
    if r.status_code not in (200, 201, 202):
        ok = False
        logs.append("❌ attendu 200/201/202")
    else:
        logs.append("✓ statut accepté")

    return {
        "name": "Étape 6 — Sanity collect",
        "ok": ok,
        "duration": round(time.time() - t0, 2),
        "logs": logs,
    }
