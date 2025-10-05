# -*- coding: utf-8 -*-
"""
E2E (simulé) FlowForms — Home → Step1→Step2→Submit
Exécution:  python manage.py runscript forms_e2e
Sans paramètre. Tout est en dur dans le script.

Objectif: diagnostiquer de bout en bout ce qui empêcherait l'utilisateur
de progresser dans le wizard et d'envoyer le formulaire.

Notes:
- On ne "clique" pas réellement (pas de navigateur). On vérifie plutôt
  que *toutes les conditions* pour que le JS progresse sont réunies,
  puis on simule la soumission côté serveur avec le même payload.
- Des snapshots sont écrits dans /tmp pour inspection rapide.
"""

from __future__ import annotations
import json
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from django.conf import settings
from django.test import Client
from django.urls import reverse, NoReverseMatch
from django.utils import timezone
from apps.common.runscript_harness import binary_harness

# ------------------------------------------------------------
# Helpers d'affichage (couleurs/emoji)
# ------------------------------------------------------------
EMOJI = {
    "ok": "✅",
    "fail": "❌",
    "warn": "⚠️",
    "info": "ℹ️",
    "step": "🧭",
    "net": "🌐",
    "dom": "🧩",
    "post": "📤",
    "cfg": "🧰",
    "snap": "📄",
    "ready": "🚀",
    "title": "🧪",
}

def c(s, color):
    codes = {
        "green": "\033[92m",
        "red": "\033[91m",
        "yellow": "\033[93m",
        "cyan": "\033[96m",
        "bold": "\033[1m",
        "dim": "\033[2m",
        "end": "\033[0m",
    }
    return f"{codes.get(color,'')}{s}{codes['end']}"

def title(msg):
    print(f"\n{EMOJI['title']}  {c(msg, 'bold')}")

def section(msg):
    print(f"\n{c('—'*80, 'dim')}\n{EMOJI['step']}  {c(msg, 'cyan')}\n{c('—'*80, 'dim')}")

def log_ok(msg):   print(f"{EMOJI['ok']}  {msg}")
def log_fail(msg): print(f"{EMOJI['fail']}  {c(msg, 'red')}")
def log_warn(msg): print(f"{EMOJI['warn']}  {c(msg, 'yellow')}")
def log_info(msg): print(f"{EMOJI['info']}  {msg}")

def snapshot(text: str, suffix: str) -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = f"/tmp/flowforms_{suffix}_{ts}.txt"
    try:
        Path(path).write_text(text, encoding="utf-8")
        log_info(f"{EMOJI['snap']}  Snapshot: {path}")
    except Exception as e:
        log_warn(f"Impossible d'écrire le snapshot {path}: {e}")
    return path

# ------------------------------------------------------------
# Parsers HTML "légers" sans dépendances externes
# ------------------------------------------------------------
RE_SCRIPT_CONFIG = re.compile(
    r'<script[^>]*data-ff-config[^>]*>(?P<json>.*?)</script>',
    re.IGNORECASE | re.DOTALL
)

RE_RUNTIME_TAG = re.compile(
    r'<script[^>]+src="[^"]*flowforms\.runtime\.js[^"]*"[^>]*>',
    re.IGNORECASE
)

def extract_ff_config(html: str) -> Optional[Dict[str, Any]]:
    m = RE_SCRIPT_CONFIG.search(html)
    if not m:
        return None
    raw = m.group("json").strip()
    # Certains templates utilisent {% json_script %} → échappements possibles
    # On tente un json.loads direct ; en cas d'échec, on essuie quelques artefacts.
    try:
        return json.loads(raw)
    except Exception:
        # fallback minimal (enlève HTML comments / script id JSONDjango)
        try:
            raw2 = raw
            raw2 = re.sub(r'<!--.*?-->', '', raw2, flags=re.DOTALL)
            raw2 = raw2.replace("&quot;", '"')
            return json.loads(raw2)
        except Exception:
            return None

def count_nodes(html: str, selector: str) -> int:
    """
    Sélecteurs ultra-rapides pour notre usage:
      - [data-ff-root]
      - [data-ff-step="X"]
      - [data-ff-field="email"] etc.
    """
    if selector == "[data-ff-root]":
        return len(re.findall(r'data-ff-root', html))
    if selector.startswith('[data-ff-step="'):
        v = selector.split('"')[1]
        return len(re.findall(rf'data-ff-step\s*=\s*"{re.escape(v)}"', html))
    if selector.startswith('[data-ff-field="'):
        v = selector.split('"')[1]
        return len(re.findall(rf'data-ff-field\s*=\s*"{re.escape(v)}"', html))
    if selector.startswith('[data-ff-'):
        # fallback générique
        attr = selector.strip("[]")
        key, _, val = attr.partition("=")
        if val:
            v = val.strip('"')
            return len(re.findall(rf'{re.escape(key)}\s*=\s*"{re.escape(v)}"', html))
        return len(re.findall(re.escape(key), html))
    # Boutons
    if selector == "[data-ff-next]":
        return len(re.findall(r'data-ff-next', html))
    if selector == "[data-ff-prev]":
        return len(re.findall(r'data-ff-prev', html))
    if selector == "[data-ff-submit]":
        return len(re.findall(r'data-ff-submit', html))
    return 0

def has_local_dnone_rule(html: str) -> bool:
    return bool(re.search(r"<style[^>]*>[^<]*\.d-none\s*\{\s*display\s*:\s*none[^}]*\}", html, re.IGNORECASE))

# ------------------------------------------------------------
# E2E "Simulé"
# ------------------------------------------------------------
@binary_harness
def run():
    title("FlowForms — E2E (simulé) : Home → Wizard → Submit")

    # ---------------- ENV ----------------
    section("Environnement")
    log_info(f"DEBUG: {settings.DEBUG}")
    log_info(f"LANGUAGE_CODE: {getattr(settings, 'LANGUAGE_CODE', '—')}")
    log_info(f"FLOWFORMS_POLICY_YAML: {getattr(settings, 'FLOWFORMS_POLICY_YAML', '—')}")
    # Liste d'apps utiles
    expected_apps = ["apps.pages", "apps.flowforms", "apps.leads"]
    present = [a for a in expected_apps if a in settings.INSTALLED_APPS]
    missing = [a for a in expected_apps if a not in settings.INSTALLED_APPS]
    if present:
        log_ok(f"Apps présentes: {', '.join(present)}")
    if missing:
        log_warn(f"Apps manquantes: {', '.join(missing)}")

    client = Client(enforce_csrf_checks=True)

    # ---------------- GET HOME ----------------
    section("Requête Home (GET /)")
    home_url = "/"
    try:
        home_url = reverse("pages:home")
    except Exception:
        pass

    res = client.get(home_url, follow=True)
    if res.status_code != 200:
        log_fail(f"GET {home_url} → {res.status_code}")
        snapshot(res.content.decode("utf-8", errors="ignore"), "home_error_html")
        return
    log_ok(f"GET {home_url} → 200")
    html = res.content.decode("utf-8", errors="ignore")
    snapshot(html, "home_html")

    # ---------------- DOM CHECKS ----------------
    section("Inspection DOM (wizard inline)")
    roots = count_nodes(html, "[data-ff-root]")
    s1 = count_nodes(html, '[data-ff-step="1"]')
    s2 = count_nodes(html, '[data-ff-step="2"]')
    s3 = count_nodes(html, '[data-ff-step="3"]')
    log_info(f"ff-root: {roots} | step1: {s1} | step2: {s2} | step3: {s3}")
    if roots >= 1 and s1 >= 1:
        log_ok("Bloc wizard présent")
    else:
        log_fail("Bloc wizard absent → l’hydrateur n’a pas injecté le wizard.")
        return

    if RE_RUNTIME_TAG.search(html):
        log_ok("Asset JS runtime détecté dans la page")
    else:
        log_warn("Runtime <script src=\"...flowforms.runtime.js\"> non détecté dans l'HTML")

    if has_local_dnone_rule(html):
        log_ok("Règle CSS locale .d-none présente (display:none)")
    else:
        log_warn("Absence de règle locale .d-none → risque d'échec du masquage/affichage des steps si CSS global interfère.")

    # ---------------- CONFIG JSON ----------------
    section("Extraction config JSON (data-ff-config)")
    cfg = extract_ff_config(html)
    if not cfg:
        log_fail("Config JSON introuvable")
        return

    flow_key = cfg.get("flow_key") or "ff"
    endpoint_url = cfg.get("endpoint_url")
    require_signed = bool(cfg.get("require_signed_token", False))
    sign_url = cfg.get("sign_url")
    ui = cfg.get("ui") or {}

    log_ok(f"flow_key = {flow_key}")
    log_info(f"endpoint_url = {endpoint_url or '—'}")
    log_info(f"require_signed_token = {require_signed}")
    if require_signed:
        log_info(f"sign_url = {sign_url or '—'}")

    # ---------------- WIZARD SERVER SENTINEL ----------------
    section("Vérification wizard serveur")
    # On tente /flows/<flow_key>/ (comme dans tes logs)
    flow_sentinel_url = f"/flows/{flow_key}/"
    flow_res = client.get(flow_sentinel_url)
    if flow_res.status_code == 200:
        log_ok(f"GET {flow_sentinel_url} → 200 (sentinel OK)")
    else:
        log_warn(f"GET {flow_sentinel_url} → {flow_res.status_code} (facultatif)")

    # ---------------- STEP 1 (validation) ----------------
    section("Étape 1 — champs & contraintes")
    email_fields = count_nodes(html, '[data-ff-field="email"]')
    if email_fields == 0:
        log_fail("Champ email introuvable (data-ff-field=\"email\")")
        return
    log_ok("Champ email présent")
    # Vérifie attributs requis/validate
    required_email = bool(re.search(r'data-ff-field="email"[^>]*data-ff-required="true"', html))
    validate_email = bool(re.search(r'data-ff-field="email"[^>]*data-ff-validate="[^"]*email[^"]*"', html))
    if required_email:
        log_ok("Email marqué requis")
    else:
        log_warn("Email NON marqué requis")
    if validate_email:
        log_ok("Validation email présente")
    else:
        log_warn("Validation email absente")

    has_next = count_nodes(html, "[data-ff-next]") > 0
    if has_next:
        log_ok("Bouton Continuer (data-ff-next) présent")
    else:
        log_fail("Bouton Continuer introuvable")
        return

    # ---------------- STEP 2 (structure) ----------------
    section("Étape 2 — structure")
    has_firstname = count_nodes(html, '[data-ff-field="first_name"]') > 0
    has_prev = count_nodes(html, "[data-ff-prev]") > 0
    has_submit = count_nodes(html, "[data-ff-submit]") > 0

    if s2 >= 1:
        log_ok("Step 2 présent dans le DOM")
    else:
        log_warn("Step 2 absent du DOM (le runtime ne pourra pas y aller)")

    log_info(f"Champs step 2 → first_name: {'OK' if has_firstname else '—'} ; prev: {'OK' if has_prev else '—'} ; submit: {'OK' if has_submit else '—'}")
    if not has_submit:
        log_fail("Aucun bouton de soumission (data-ff-submit) → impossible de terminer le wizard")
        return

    # ---------------- SUBMIT (simulation payload JS) ----------------
    section("Soumission — POST endpoint de collecte")

    # 1) Email valide (utilisé par défaut)
    test_email = "tester.e2e@example.com"
    test_first_name = "Tester"
    # 2) Contexte & form_kind comme le runtime
    form_kind = cfg.get("form_kind") or "email_ebook"
    context = cfg.get("context") or {}
    idem_key = str(uuid.uuid4())

    payload = {
        "form_kind": form_kind,
        "email": test_email,
        "first_name": test_first_name,
        "client_ts": datetime.utcnow().isoformat() + "Z",
        "context": context,
        "honeypot": "",  # le JS enverrait la valeur du [data-ff-honeypot] (vide ici)
    }

    # 3) Signature optionnelle (si activée côté composant)
    if require_signed:
        if not sign_url:
            log_fail("Signature requise mais sign_url manquant dans la config JSON")
            return
        log_info("Signature du payload…")
        sign_res = client.post(sign_url, data=json.dumps({"payload": payload}),
                               content_type="application/json",
                               HTTP_X_CSRFTOKEN=client.cookies.get("csrftoken", ""),
                               HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        if sign_res.status_code == 200:
            try:
                signed = json.loads(sign_res.content.decode("utf-8"))
                token = signed.get("token") or signed.get("signed_token")
                if token:
                    payload["signed_token"] = token
                    log_ok("Signature obtenue")
                else:
                    log_warn("Réponse de signature 200 mais sans token")
            except Exception as e:
                log_warn(f"Réponse signature invalide: {e}")
        else:
            log_fail(f"Signature HTTP {sign_res.status_code} ; impossible de continuer")
            snapshot(sign_res.content.decode("utf-8", errors="ignore"), "sign_error_json")
            return

    # 4) Endpoint de collecte
    if not endpoint_url:
        # fallback: essayer via urlname settings
        try:
            endpoint_url = reverse(getattr(settings, "FLOWFORMS_ENDPOINT_COLLECT_URLNAME", "leads:collect"))
            log_info(f"endpoint_url (fallback reverse) = {endpoint_url}")
        except NoReverseMatch:
            log_fail("endpoint_url introuvable (ni dans config JSON ni via reverse)")
            return

    # 5) POST JSON (avec idempotency + CSRF si dispo)
    headers = {
        "HTTP_X_IDEMPOTENCY_KEY": idem_key,
        "HTTP_X_CSRFTOKEN": client.cookies.get("csrftoken", ""),
        "HTTP_X_REQUESTED_WITH": "XMLHttpRequest",
    }
    post_res = client.post(endpoint_url, data=json.dumps(payload), content_type="application/json", **headers)
    body = post_res.content.decode("utf-8", errors="ignore")
    snapshot(body, "collect_response")

    if post_res.status_code == 202:
        log_ok("Soumission acceptée (202) — FIN OK (le wizard passerait à l’étape 3)")
    elif post_res.status_code == 400:
        log_warn("Soumission refusée (400) — erreurs de validation")
        try:
            err = json.loads(body)
            log_info(f"Erreurs: {json.dumps(err, ensure_ascii=False)}")
        except Exception:
            pass
    elif post_res.status_code == 429:
        log_warn("Rate limited (429) — throttling")
    elif post_res.status_code == 403 and "csrf" in body.lower():
        log_warn("403 CSRF — l’endpoint exige un CSRF token. Vérifie la politique CSRF de la vue.")
    else:
        log_fail(f"Soumission renvoie HTTP {post_res.status_code}")

    # 6) Rejoue la requête avec la *même* idempotency key (doit être idempotent)
    log_info("Rejoue la soumission avec la même idempotency key (idempotency check)")
    post_res2 = client.post(endpoint_url, data=json.dumps(payload), content_type="application/json", **headers)
    log_info(f"HTTP {post_res2.status_code} (attendu: 202, 200, 409… selon ta sémantique)")

    # ---------------- RÉSUMÉ ----------------
    section("Résumé")
    print(
        f"{EMOJI['dom']}  Wizard: root={roots} s1={s1} s2={s2} s3={s3} | "
        f"{EMOJI['cfg']} flow={flow_key} signed={require_signed} endpoint={endpoint_url}"
    )
    log_info("Si le POST est 202, le runtime basculera en step 3 (merci). "
             "Si l’UI ne change pas côté navigateur, c’est un souci de CSS (d-none) ou d’assets.")
