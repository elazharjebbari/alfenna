# apps/atelier/scripts/formfront/tests_scripts/test_5b_child_cache_stability.py
from __future__ import annotations
import time
from django.test.client import RequestFactory
from apps.atelier.components.forms.wizard.hydrators import hydrate
from apps.common.runscript_harness import binary_harness

NAME = "Étape 5.B — Variation stable (même contenu, formats différents → même SHA1)"

@binary_harness
def run():
    t0 = time.time(); logs = []; ok = True
    rf = RequestFactory()

    cfg_min = '{"flow_key":"A","endpoint_url":"/api","form_kind":"x","context":{}}'
    cfg_pretty = '''
    {
      "context":{},
      "form_kind":"x",
      "endpoint_url":"/api",
      "flow_key":"A"
    }'''.strip()

    c1 = hydrate(rf.get("/"), params={"flow_key":"A", "config_json": cfg_min})
    c2 = hydrate(rf.get("/"), params={"flow_key":"A", "config_json": cfg_pretty})

    logs.append(f"sha1 #1 = {c1['config_sha1']}  /  sha1 #2 = {c2['config_sha1']}")
    if c1["config_sha1"] != c2["config_sha1"]:
        ok = False; logs.append("❌ SHA1 différents alors que le contenu est sémantiquement identique")

    return {"name": NAME, "ok": ok, "duration": round(time.time()-t0,2), "logs": logs}