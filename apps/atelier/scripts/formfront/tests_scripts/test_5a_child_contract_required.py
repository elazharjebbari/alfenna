# apps/atelier/scripts/formfront/tests_scripts/test_5a_child_contract_required.py
from __future__ import annotations
import time
from django.test.client import RequestFactory
from apps.atelier.components.forms.wizard.hydrators import hydrate
from apps.common.runscript_harness import binary_harness

NAME = "Étape 5.A — Contrat child strict (required + JSON parseable)"

@binary_harness
def run():
    t0 = time.time(); logs = []; ok = True
    rf = RequestFactory()

    # 1) Cas OK — params complets valides
    params_ok = {
        "flow_key": "checkout_intent_flow",
        "config_json": '{"flow_key":"checkout_intent_flow","endpoint_url":"/api/leads/collect/","form_kind":"email_ebook","context":{}}'
    }
    try:
        ctx_ok = hydrate(rf.get("/"), params=params_ok)
        if not (ctx_ok.get("config_json") and ctx_ok.get("flow_key") and ctx_ok.get("config_sha1")):
            ok = False; logs.append("❌ Contexte incomplet pour cas OK")
        else:
            logs.append(f"✅ OK → flow_key={ctx_ok['flow_key']} sha1={ctx_ok['config_sha1']}")
    except Exception as e:
        ok = False; logs.append(f"❌ Cas OK a levé une exception inattendue: {e}")

    # 2) Cas KO — flow_key vide
    try:
        hydrate(rf.get("/"), params={
            "flow_key": "   ",
            "config_json": '{"form_kind":"x","endpoint_url":"/api"}'
        })
        ok = False; logs.append("❌ KO(flow_key vide): aucune exception levée")
    except Exception as e:
        logs.append(f"✅ KO(flow_key vide) → {e}")

    # 3) Cas KO — config_json non parseable
    try:
        hydrate(rf.get("/"), params={
            "flow_key": "ff",
            "config_json": "{not-json"
        })
        ok = False; logs.append("❌ KO(config_json invalide): aucune exception levée")
    except Exception as e:
        logs.append(f"✅ KO(config_json invalide) → {e}")

    return {"name": NAME, "ok": ok, "duration": round(time.time()-t0,2), "logs": logs}