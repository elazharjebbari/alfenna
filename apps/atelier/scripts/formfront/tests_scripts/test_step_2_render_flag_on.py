import time, re
from ._utils import get_home_html, count, FlagSwap
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    t0 = time.time(); logs = []; ok = True
    with FlagSwap("FLOWFORMS_USE_CHILD_COMPOSE", True):
        client, status, html = get_home_html()
    if status != 200: ok=False; logs.append(f"❌ GET / → {status}")
    # Slot enfant attendu
    if "<!-- FF: composed child (slot) -->" not in html:
        ok=False; logs.append("❌ slot enfant absent (compose ON)")
    if "<!-- FF: wizard via renderer -->" in html:
        ok=False; logs.append("❌ fallback renderer encore utilisé (compose ON)")
    if count("ff-root", html) < 1: ok=False; logs.append("❌ wizard DOM [data-ff-root] absent")
    # Un seul runtime
    runtime_tags = len(re.findall(r'flowforms\.runtime\.js', html, flags=re.I))
    if runtime_tags != 1: ok=False; logs.append(f"❌ runtime attendu 1, trouvé {runtime_tags}")
    if ok:
        logs += ["✅ Slot enfant rendu", "✅ Wizard DOM présent", "✅ Runtime unique (x1)"]
    return {"name":"Étape 2 — Rendu flag ON (compose)", "ok":ok, "duration":round(time.time()-t0,2), "logs":logs}
