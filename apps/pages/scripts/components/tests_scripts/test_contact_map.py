import time
from pathlib import Path

from django.conf import settings
from django.template import loader

from apps.common.runscript_harness import binary_harness

ANSI = {"G": "\033[92m", "R": "\033[91m", "B": "\033[94m", "X": "\033[0m"}
NAME = "contact/map — Template markers"


@binary_harness
def run():
    started = time.time()
    logs, ok = [], True
    tpl_name = "components/contact/map.html"
    tpl = loader.get_template(tpl_name)
    origin = getattr(tpl, "origin", None)
    logs.append(f"Template loader → {tpl_name} (origin={getattr(origin, 'name', 'n/a')})")

    origin_path = None
    if origin and origin.name:
        origin_path = Path(origin.name)
    else:
        for directory in settings.TEMPLATES[0]["DIRS"]:
            candidate = Path(directory) / tpl_name
            if candidate.exists():
                origin_path = candidate
                break

    if not origin_path or not origin_path.exists():
        ok = False
        logs.append(f"{ANSI['R']}Fichier introuvable: {tpl_name}{ANSI['X']}")
        return {"ok": ok, "name": NAME, "duration": round(time.time() - started, 2), "logs": logs}

    text = origin_path.read_text(encoding="utf-8")
    marker = "{{ map_embed_url }}"
    has_marker = marker in text
    logs.append(f"Présence variable {marker}: {has_marker}")
    if not has_marker:
        ok = False

    banned = ["google.com/maps", "lumieresacademy"]
    for snippet in banned:
        if snippet in text:
            ok = False
            logs.append(f"{ANSI['R']}❌ Hard-coded détecté: {snippet}{ANSI['X']}")

    return {"ok": ok, "name": NAME, "duration": round(time.time() - started, 2), "logs": logs}
