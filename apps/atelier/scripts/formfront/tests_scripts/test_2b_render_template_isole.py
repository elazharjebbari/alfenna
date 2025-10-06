import time
from django.template import loader
from apps.common.runscript_harness import binary_harness

NAME = "Étape 2.B — Render template isolé (compose ON/OFF)"

def _short(s, around=None, width=160):
    if not s:
        return ""
    if not around:
        return (s[:width] + "…") if len(s) > width else s
    i = s.find(around)
    if i < 0:
        return (s[:width] + "…") if len(s) > width else s
    start = max(0, i-80)
    end = min(len(s), i+len(around)+80)
    return s[start:end].replace("\n", " ")

@binary_harness
def run():
    t0 = time.time()
    logs, ok = [], True

    tpl = loader.get_template("components/forms/shell.html")

    # 1) Compose ON -> children.wizard fourni
    ctx_on = {
        "title_html": "Titre",
        "children": {"wizard": "<div id='kid'>KID</div>"},
        # rien d’autre
    }
    html_on = tpl.render(ctx_on)
    has_slot = 'data-ff-slot="wizard"' in html_on
    no_legacy = 'data-ff-renderer="legacy"' not in html_on
    logs.append("Compose ON → extrait: " + _short(html_on, 'data-ff-slot="wizard"'))

    if not has_slot:
        ok=False; logs.append("❌ Compose ON: slot data-ff-slot=\"wizard\" absent dans le rendu.")
    if not no_legacy:
        ok=False; logs.append("❌ Compose ON: rendu ne doit PAS contenir data-ff-renderer=\"legacy\".")

    # 2) Compose OFF -> pas de children, mais wizard_html fourni
    ctx_off = {
        "title_html": "Titre",
        "wizard_html": "<div class='legacy-wiz'>WIZ</div>",
    }
    html_off = tpl.render(ctx_off)
    has_legacy = 'data-ff-renderer="legacy"' in html_off
    no_slot = 'data-ff-slot="wizard"' not in html_off
    logs.append("Compose OFF → extrait: " + _short(html_off, 'data-ff-renderer="legacy"'))

    if not has_legacy:
        ok=False; logs.append("❌ Compose OFF: marque data-ff-renderer=\"legacy\" absente dans le rendu.")
    if not no_slot:
        ok=False; logs.append("❌ Compose OFF: le slot wizard ne doit PAS être présent.")

    return {"ok": ok, "name": NAME, "duration": round(time.time()-t0, 2), "logs": logs}