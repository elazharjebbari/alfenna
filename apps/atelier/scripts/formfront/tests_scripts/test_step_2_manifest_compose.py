import time, re
from pathlib import Path
from django.conf import settings
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    t0 = time.time()
    logs = []
    ok = True
    path = Path(settings.BASE_DIR) / "templates" / "components" / "forms" / "manifest"
    if not path.exists():
        return {"name":"Étape 2 — Manifest compose", "ok":False, "duration":0, "logs":[f"❌ Fichier absent: {path}"]}

    text = path.read_text(encoding="utf-8")
    for needle in ["compose:", "children:", "wizard", "forms/wizard_generic"]:
        if needle not in text:
            ok = False; logs.append(f"❌ '{needle}' manquant dans manifest")
    if ok: logs.append("✅ compose.children.wizard → forms/wizard_generic déclaré")
    return {"name":"Étape 2 — Manifest compose", "ok":ok, "duration":round(time.time()-t0,2), "logs":logs}
