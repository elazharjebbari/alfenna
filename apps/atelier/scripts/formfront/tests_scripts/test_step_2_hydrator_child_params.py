import time
from django.test import RequestFactory
from apps.atelier.components.forms.shell.hydrators import hydrate
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    t0 = time.time(); logs = []; ok = True
    rf = RequestFactory(); req = rf.get("/")
    ctx = hydrate(req, params={})
    child = ctx.get("child") or {}
    if not child.get("flow_key"): ok=False; logs.append("❌ child.flow_key absent")
    if not child.get("config_json"): ok=False; logs.append("❌ child.config_json absent")
    if ok:
        logs.append(f"✅ child.flow_key={child['flow_key']}")
        logs.append("✅ child.config_json présent")
    return {"name":"Étape 2 — Hydrateur : params enfant", "ok":ok, "duration":round(time.time()-t0,2), "logs":logs}
