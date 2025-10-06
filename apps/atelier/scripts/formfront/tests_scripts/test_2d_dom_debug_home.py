import re, time
from django.test import Client
from django.test.utils import override_settings
from apps.common.runscript_harness import binary_harness

NAME = "Étape 2.D — DOM Home (extraits ciblés ff-shell)"

def _extract_ff_shell(html, width=400):
    m = re.search(r'(<div[^>]+class="[^"]*ff-shell[^"]*"[^>]*>.*?</div>)', html, re.DOTALL|re.IGNORECASE)
    if not m:
        return "(ff-shell introuvable)"
    frag = m.group(1)
    frag = re.sub(r"\s+", " ", frag)
    return frag[:width] + ("…" if len(frag) > width else "")

@binary_harness
def run():
    t0 = time.time(); logs = []; ok = True
    c = Client()

    # OFF
    with override_settings(FLOWFORMS_COMPONENT_ENABLED=False):
        r = c.get("/")
        html = r.content.decode("utf-8", errors="ignore")
        frag = _extract_ff_shell(html)
        logs.append("OFF → extrait ff-shell: " + frag)
        has_legacy = 'data-ff-renderer="legacy"' in frag
        if not has_legacy:
            ok=False; logs.append("❌ OFF: marque data-ff-renderer='legacy' absente dans la home.")

    # ON
    with override_settings(FLOWFORMS_COMPONENT_ENABLED=True):
        r = c.get("/")
        html = r.content.decode("utf-8", errors="ignore")
        frag = _extract_ff_shell(html)
        logs.append("ON  → extrait ff-shell: " + frag)
        has_slot = 'data-ff-slot="wizard"' in frag
        if not has_slot:
            ok=False; logs.append("❌ ON: slot data-ff-slot='wizard' absent dans la home.")

    return {"ok": ok, "name": NAME, "duration": round(time.time()-t0,2), "logs": logs}