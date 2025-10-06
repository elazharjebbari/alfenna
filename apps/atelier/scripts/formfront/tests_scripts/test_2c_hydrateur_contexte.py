import time
from django.test.client import RequestFactory
from django.test.utils import override_settings
from apps.common.runscript_harness import binary_harness

ANSI = {"G":"\033[92m","R":"\033[91m","Y":"\033[93m","B":"\033[94m","X":"\033[0m","C":"\033[96m"}
NAME = "Étape 2.C — Hydrateur: structure du contexte (flag ON/OFF)"

def _import_hydrator(logs):
    # Plusieurs chemins possibles, on essaie en cascade
    candidates = [
        "apps.atelier.components.forms.shell.hydrators",
        "apps.atelier.components.forms.shell import hydrators",
    ]
    for c in candidates:
        try:
            mod = __import__(c, fromlist=["*"])
            logs.append(f"Import hydrators OK via '{c}'")
            return mod
        except Exception as e:
            logs.append(f"Import '{c}' échoué: {e}")
    return None

@binary_harness
def run():
    t0 = time.time()
    logs, ok = [], True

    hydrators = _import_hydrator(logs)
    if not hydrators or not hasattr(hydrators, "hydrate"):
        logs.append(f"{ANSI['R']}Impossible d’importer hydrate(){ANSI['X']}")
        return {"ok": False, "name": NAME, "duration": round(time.time()-t0,2), "logs": logs}

    rf = RequestFactory()

    # OFF
    with override_settings(FLOWFORMS_COMPONENT_ENABLED=False):
        req = rf.get("/")
        ctx_off = hydrators.hydrate(req)
        logs.append(f"OFF → keys: {sorted(list(ctx_off.keys()))}")
        has_children = bool(ctx_off.get("children"))
        has_wizard_html = "wizard_html" in ctx_off and bool(ctx_off.get("wizard_html"))
        if has_children:
            ok=False; logs.append("❌ OFF: le contexte ne doit pas exposer 'children'.")
        if not has_wizard_html:
            ok=False; logs.append("❌ OFF: 'wizard_html' attendu (fallback).")

    # ON
    with override_settings(FLOWFORMS_COMPONENT_ENABLED=True):
        req = rf.get("/")
        ctx_on = hydrators.hydrate(req)
        logs.append(f"ON  → keys: {sorted(list(ctx_on.keys()))}")
        has_children = bool(ctx_on.get("children"))
        child_wizard = has_children and "wizard" in ctx_on["children"]
        has_wizard_html = "wizard_html" in ctx_on and bool(ctx_on.get("wizard_html"))
        if not child_wizard:
            ok=False; logs.append("❌ ON: children.wizard attendu.")
        if has_wizard_html:
            ok=False; logs.append("❌ ON: 'wizard_html' ne doit pas être fourni en compose.")

    return {"ok": ok, "name": NAME, "duration": round(time.time()-t0,2), "logs": logs}