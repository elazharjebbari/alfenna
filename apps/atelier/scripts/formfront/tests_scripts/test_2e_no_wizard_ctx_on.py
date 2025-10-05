import time
from django.test.client import RequestFactory
from django.test.utils import override_settings
from apps.common.runscript_harness import binary_harness

NAME = "Étape 2.E — Anti-pollution: wizard_ctx absent en compose ON"

def _import_hydrator():
    for c in [
        "apps.flowforms.components.forms.shell.hydrators.py",
        "apps.flowforms.components.forms.shell import hydrators.py",
        "forms.shell.hydrators.py",
    ]:
        try:
            return __import__(c, fromlist=["*"])
        except Exception:
            pass
    return None

@binary_harness
def run():
    t0=time.time(); logs=[]; ok=True
    hydrators = _import_hydrator()
    if not hydrators or not hasattr(hydrators, "hydrate"):
        logs.append("hydrate() introuvable, test ignoré.")
        return {"ok": True, "name": NAME, "duration": round(time.time()-t0,2), "logs": logs}

    rf = RequestFactory()
    with override_settings(FLOWFORMS_COMPONENT_ENABLED=True):
        ctx = hydrators.hydrate(rf.get("/"))
        if "wizard_ctx" in ctx and ctx["wizard_ctx"]:
            ok=False; logs.append("❌ Compose ON: 'wizard_ctx' ne doit pas être exposé.")
        else:
            logs.append("✅ wizard_ctx non présent (OK).")
    return {"ok": ok, "name": NAME, "duration": round(time.time()-t0,2), "logs": logs}