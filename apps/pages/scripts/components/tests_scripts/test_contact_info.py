import time
from pathlib import Path

from django.conf import settings
from django.template import loader

from apps.common.runscript_harness import binary_harness

ANSI = {"G": "\033[92m", "R": "\033[91m", "Y": "\033[93m", "B": "\033[94m", "X": "\033[0m", "C": "\033[96m"}
NAME = "contact/info — Template markers"


@binary_harness
def run():
    t0 = time.time()
    logs, ok = [], True
    tpl_name = "components/contact/info.html"
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
        return {"ok": ok, "name": NAME, "duration": round(time.time() - t0, 2), "logs": logs}

    text = origin_path.read_text(encoding="utf-8")
    expected_vars = {
        "phone_tel": ["{{ phone_tel"],
        "phone_display": ["{{ phone_display"],
        "phone_title": ["{{ phone_title", "render_string phone_title"],
        "email": ["{{ email"],
        "email_title": ["{{ email_title", "render_string email_title"],
        "address_url": ["{{ address_url"],
        "address_text": ["{{ address_text", "render_string address_text"],
        "address_title": ["{{ address_title", "render_string address_title"],
    }

    for var, patterns in expected_vars.items():
        has_marker = any(pattern in text for pattern in patterns)
        logs.append(f"Présence variable {var}: {has_marker}")
        if not has_marker:
            ok = False

    banned = ["+212", "@lumiereacademy.com", "Rue Patrice Lumumba"]
    for snippet in banned:
        if snippet in text:
            ok = False
            logs.append(f"{ANSI['R']}❌ Hard-coded détecté: {snippet}{ANSI['X']}")

    return {"ok": ok, "name": NAME, "duration": round(time.time() - t0, 2), "logs": logs}
