import time
from pathlib import Path
from django.conf import settings
from django.template import loader
from apps.common.runscript_harness import binary_harness

ANSI = {"G":"\033[92m","R":"\033[91m","Y":"\033[93m","B":"\033[94m","X":"\033[0m","C":"\033[96m"}

NAME = "Étape 2.A — Template markers (contenu fichier)"

@binary_harness
def run():
    t0 = time.time()
    logs = []
    ok = True

    tpl_name = "components/forms/shell.html"
    tpl = loader.get_template(tpl_name)
    origin = getattr(tpl, "origin", None)
    logs.append(f"Template loader → {tpl_name} (origin={getattr(origin, 'name', 'n/a')})")

    # On lit le fichier réel pour vérifier les marqueurs (plus fiable qu’un render)
    origin_path = None
    if origin and origin.name:
        origin_path = Path(origin.name)
    else:
        # fallback: on tente de le retrouver via TEMPLATES['DIRS']
        for d in settings.TEMPLATES[0]["DIRS"]:
            p = Path(d) / tpl_name
            if p.exists():
                origin_path = p
                break

    if not origin_path or not origin_path.exists():
        ok = False
        logs.append(f"{ANSI['R']}Fichier introuvable: {tpl_name}{ANSI['X']}")
        return {"ok": ok, "name": NAME, "duration": round(time.time()-t0, 2), "logs": logs}

    text = origin_path.read_text(encoding="utf-8")

    exp_slot = 'data-ff-slot="wizard"'
    exp_legacy = 'data-ff-renderer="legacy"'

    has_slot = (exp_slot in text)
    has_legacy = (exp_legacy in text)

    logs.append(f"Marqueur compose (slot): {has_slot} — recherche '{exp_slot}'")
    logs.append(f"Marqueur legacy(renderer): {has_legacy} — recherche '{exp_legacy}'")

    if not has_slot:
        ok = False
        logs.append(f"{ANSI['R']}❌ Manque le slot compose dans le fichier template.{ANSI['X']}")
    if not has_legacy:
        ok = False
        logs.append(f"{ANSI['R']}❌ Manque la marque legacy(renderer) dans le fichier template.{ANSI['X']}")

    return {"ok": ok, "name": NAME, "duration": round(time.time()-t0, 2), "logs": logs}