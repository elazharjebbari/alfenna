from __future__ import annotations
import time
from django.conf import settings
from django.test import Client
from django.urls import reverse
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    t0 = time.time()
    logs = []
    ok = True

    # 1) Flags & defaults présents
    required_settings = [
        "FLOWFORMS_POLICY_YAML",
        "FLOWFORMS_DEFAULT_FLOW_KEY",
        "FLOWFORMS_ENDPOINT_COLLECT_URLNAME",
        "FLOWFORMS_REQUIRE_SIGNED",
        "FLOWFORMS_SIGN_URLNAME",
        "FLOWFORMS_COMPONENT_ENABLED",
    ]
    for key in required_settings:
        if not hasattr(settings, key):
            logs.append(f"❌ Manque settings.{key}")
            ok = False
        else:
            logs.append(f"✅ {key} = {getattr(settings, key)}")

    # 2) Smoke test home
    client = Client()
    try:
        home_url = reverse("pages:home")
    except Exception:
        home_url = "/"

    res = client.get(home_url)
    if res.status_code != 200:
        ok = False
        logs.append(f"❌ GET {home_url} → {res.status_code}")
    else:
        logs.append(f"✅ GET {home_url} → 200")

    # 3) Présence runtime & bloc wizard (chemin actuel par include)
    html = res.content.decode("utf-8", errors="ignore")
    if "flowforms.runtime.js" in html:
        logs.append("✅ Runtime détecté dans l’HTML")
    else:
        logs.append("⚠️ Runtime non détecté (vérifier assets parent)")

    if 'data-ff-root' in html:
        logs.append("✅ Wizard DOM présent (root)")
    else:
        logs.append("⚠️ Wizard DOM non trouvé (root)")

    print(logs)
    return {
        "name": "Étape 0 — Feature flag & Smoke",
        "ok": ok,
        "duration": round(time.time() - t0, 2),
        "logs": logs,
    }
