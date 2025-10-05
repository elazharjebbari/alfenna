"""
runscript formfront.tests_scripts.test_6_signature_diagnostic

But:
- Diagnostiquer les erreurs "Token invalide." en comparant précisément
  (payload signé) vs (payload posté).
- Montrer plusieurs cas: OK, ajout/suppression de champs, ts différent, TTL expiré,
  header d'idempotence manquant, etc.

Exécution:
  python manage.py runscript formfront.tests_scripts.test_6_signature_diagnostic
"""

import time, hmac, hashlib, json, copy, uuid
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from django.conf import settings
from django.core.cache import cache
from apps.leads.antispam import verify_signed_token
from apps.common.runscript_harness import binary_harness


def _now_iso():
    return timezone.now().isoformat()


def _jdump(d):
    # JSON canonique pour calcul MD5 côté client & logs lisibles
    # IMPORTANT: separators=(",", ":") => élimine les espaces
    return json.dumps(d, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _md5_payload(d):
    # On exclut "signed_token" de la signature, comme côté serveur
    return hashlib.md5(
        _jdump({k: v for k, v in d.items() if k != "signed_token"}).encode("utf-8")
    ).hexdigest()


def _make_local_token(payload_dict, *, ts=None, secret=None):
    ts = ts or int(time.time())
    secret = secret or getattr(settings, "LEADS_SIGNING_SECRET", settings.SECRET_KEY)
    msg = _md5_payload(payload_dict)
    mac = hmac.new(secret.encode("utf-8"), f"{ts}.{msg}".encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{ts}.{mac}", msg


def _diff_payloads(a, b):
    """
    a = payload signé
    b = payload posté
    """
    ka, kb = set(a.keys()), set(b.keys())
    added = sorted(list(kb - ka))
    removed = sorted(list(ka - kb))
    changed = []
    for k in sorted(ka & kb):
        va, vb = a[k], b[k]
        if va != vb:
            changed.append((k, va, vb))
    return added, removed, changed


def _pretty_change(val, maxlen=120):
    s = repr(val)
    return (s if len(s) <= maxlen else s[:maxlen] + "…")


def _run_case(name, client, sign_url, collect_url, signed_payload, posted_payload, *,
              expect_status=(200, 201, 202), with_idem=True, idem_key=None, local_old_ts=None):
    logs = []
    logs.append(f"=== {name} ===")

    # 1) signature (endpoint OU locale pour TTL expiré)
    if local_old_ts is not None:
        token, msg_signed = _make_local_token(signed_payload, ts=local_old_ts)
        logs.append("Token généré localement (ts ancien) — pas de call /sign")
        sign_status = 200
    else:
        r_sign = client.post(sign_url, data={"payload": signed_payload}, content_type="application/json")
        sign_status = r_sign.status_code
        try:
            token = (r_sign.json() or {}).get("signed_token", "")
        except Exception:
            token = ""
        msg_signed = _md5_payload(signed_payload)

    logs.append(f"Sign status: {sign_status}  token_present={bool(token)}")
    logs.append(f"MD5(signed_payload) = {msg_signed}")

    if sign_status != 200 or not token:
        logs.append("Echec signature — on s'arrête pour ce cas.")
        return {"ok": False, "duration": 0.0, "logs": logs}

    # 2) Diffs entre payload signé et posté
    added, removed, changed = _diff_payloads(signed_payload, posted_payload)
    if added or removed or changed:
        logs.append("Diff entre payload SIGNÉ et POSTÉ:")
        if added:
            logs.append(f"  + Ajoutés lors du POST : {added}")
        if removed:
            logs.append(f"  - Supprimés avant POST : {removed}")
        if changed:
            for k, va, vb in changed[:20]:
                logs.append(f"  ~ {k}: {_pretty_change(va)}  =>  {_pretty_change(vb)}")
            if len(changed) > 20:
                logs.append(f"  ... {len(changed)-20} changements supplémentaires")
    else:
        logs.append("Aucun diff: POST identique au payload signé.")

    # 3) Vérification locale (rejoue l’algo serveur)
    msg_posted = _md5_payload(posted_payload)
    local_valid = verify_signed_token(token, msg_posted, max_age_s=7200)
    logs.append(f"MD5(posted_payload) = {msg_posted}")
    logs.append(f"Local verify(token, MD5(posted)) → {local_valid}")

    # 4) POST collect — on envoie EXACTEMENT le même JSON (canon)
    sending = copy.deepcopy(posted_payload)
    sending["signed_token"] = token
    headers = {}
    if with_idem:
        headers["HTTP_X_IDEMPOTENCY_KEY"] = idem_key or f"diag-{int(time.time()*1000)}"

    payload_to_send = _jdump(sending)  # canon strict
    r = client.post(collect_url, data=payload_to_send, content_type="application/json", **headers)
    body_text = r.content.decode(errors="ignore")
    logs.append(f"POST {collect_url} → status={r.status_code} body={body_text[:300]}")

    ok = (r.status_code in expect_status)
    logs.append("✓ statut conforme aux attentes" if ok else "✗ statut inattendu")

    # 5) Hint de cohérence (si local_valid ≠ serveur)
    accepted = 200 <= r.status_code < 300
    if local_valid and not accepted:
        logs.append("⚠ Localement VALIDE, serveur a refusé.")
    if (not local_valid) and accepted:
        logs.append("⚠ Localement INVALIDE, serveur a accepté.")

    return {"ok": ok, "status": r.status_code, "local_valid": local_valid, "server_body": body_text[:1000], "logs": logs}


@binary_harness
def run():
    t0 = time.time()
    logs = []
    ok = True

    # Évite toute flakiness (dédup/idempotence) sur un environnement réutilisé
    cache.clear()

    c = Client()
    sign_url = reverse("leads:sign")
    collect_url = reverse("leads:collect")

    # Payload de base "propre", avec unicité à chaque run
    uniq = uuid.uuid4().hex[:8]
    base = {
        "form_kind": "email_ebook",
        "email": f"diag+{uniq}@example.com",
        "client_ts": _now_iso(),
        "honeypot": "",
    }

    results = []

    # A) Cas OK — signer et poster EXACTEMENT le même payload
    results.append(_run_case(
        "A) Exact same payload (should PASS)",
        c, sign_url, collect_url,
        signed_payload=base,
        posted_payload=copy.deepcopy(base),
        expect_status=(200, 201, 202),
        with_idem=True,
        idem_key=f"diag-a-{uniq}",
    ))

    # B) Ajout d'un champ après signature (ex: context={}) → devrait FAIL (ANTIFORGERY)
    with_context = copy.deepcopy(base)               # signé SANS 'context'
    posted_plus_ctx = copy.deepcopy(base)            # posté AVEC 'context'
    posted_plus_ctx["context"] = {}
    results.append(_run_case(
        "B) Ajout d'un champ après signature: context={}",
        c, sign_url, collect_url,
        signed_payload=with_context,
        posted_payload=posted_plus_ctx,
        expect_status=(400,),
        with_idem=True,
        idem_key=f"diag-b-{uniq}",
    ))

    # C) Suppression de 'honeypot' entre signature et POST → FAIL
    signed_with_hp = copy.deepcopy(base)             # honeypot = ""
    posted_without_hp = {k: v for k, v in base.items() if k != "honeypot"}
    results.append(_run_case(
        "C) Suppression de 'honeypot' avant POST",
        c, sign_url, collect_url,
        signed_payload=signed_with_hp,
        posted_payload=posted_without_hp,
        expect_status=(400,),
        with_idem=True,
        idem_key=f"diag-c-{uniq}",
    ))

    # D) Changement de format de client_ts → FAIL
    changed_ts = copy.deepcopy(base)
    changed_ts_narrow = copy.deepcopy(base)
    changed_ts_narrow["client_ts"] = base["client_ts"][:19]  # tronqué
    results.append(_run_case(
        "D) client_ts tronqué entre signature et POST",
        c, sign_url, collect_url,
        signed_payload=changed_ts,
        posted_payload=changed_ts_narrow,
        expect_status=(400,),
        with_idem=True,
        idem_key=f"diag-d-{uniq}",
    ))

    # E) TTL expiré: token généré localement avec timestamp vieux de 3h → FAIL
    old_ts = int(time.time()) - 3 * 3600  # > max_age_s=7200
    results.append(_run_case(
        "E) TTL expiré (token vieux de 3h)",
        c, sign_url, collect_url,
        signed_payload=base,
        posted_payload=copy.deepcopy(base),
        expect_status=(400,),
        with_idem=True,
        idem_key=f"diag-e-{uniq}",
        local_old_ts=old_ts,
    ))

    # F) Idempotency manquant → 400 (même avec bon token)
    results.append(_run_case(
        "F) Idempotency header manquant (devrait 400)",
        c, sign_url, collect_url,
        signed_payload=base,
        posted_payload=copy.deepcopy(base),
        expect_status=(400,),
        with_idem=False,  # pas de X-Idempotency-Key
    ))

    # Récapitulatif lisible par run_all
    logs.append("=== Résumé ===")
    for r in results:
        if not r:
            continue
        _ok = r.get("ok", False)
        logs.append(f"- {('OK' if _ok else 'FAIL'):4} | status={r.get('status')} | local_valid={r.get('local_valid')}")

    duration = round(time.time() - t0, 2)
    ok = ok and all(r.get("ok", False) for r in results)

    print("\n"*5)
    print(" \n".join(logs))
    return {
        "name": "Étape 6 — Diagnostic signature HMAC (strict)",
        "ok": ok,
        "duration": duration,
        "logs": logs + sum((r.get("logs", []) for r in results), []),
    }
