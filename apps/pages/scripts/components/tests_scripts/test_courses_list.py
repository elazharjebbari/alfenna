import time

from django.core.cache import cache
from django.core.management import call_command
from django.test import Client

from apps.common.runscript_harness import binary_harness

ANSI = {"G": "\033[92m", "R": "\033[91m", "B": "\033[94m", "X": "\033[0m"}
NAME = "courses/list — Intégration page /test"


@binary_harness
def run():
    started = time.time()
    logs, ok = [], True

    call_command("loaddata", "alfenna/fixtures/catalog_courses.json", verbosity=0)
    logs.append("Fixtures catalog_courses.json chargées.")
    cache.clear()

    client = Client()
    response = client.get("/test")
    if response.status_code != 200:
        logs.append(f"{ANSI['R']}GET /test → {response.status_code}{ANSI['X']}")
        return {"ok": False, "name": NAME, "duration": round(time.time() - started, 2), "logs": logs}

    html = response.content.decode()
    has_demo = "Cours Démo" in html
    has_candles = "Fabrication de Bougies 101" in html
    logs.append(f"Titre cours présent: {has_demo or has_candles}")
    if not (has_demo or has_candles):
        ok = False

    has_fallback = "placehold.co/600x402" in html
    logs.append(f"Fallback image détecté: {has_fallback}")
    if not has_fallback:
        ok = False

    return {"ok": ok, "name": NAME, "duration": round(time.time() - started, 2), "logs": logs}
