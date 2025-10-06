import time
from importlib import import_module

from django.conf import settings
from django.core.management import call_command

from apps.common.runscript_harness import binary_harness

ANSI = {"G": "\033[92m", "R": "\033[91m", "B": "\033[94m", "X": "\033[0m"}
NAME = "course_detail/sidebar — Hydrateur calcule prix/promo"


@binary_harness
def run():
    started = time.time()
    logs, ok = [], True

    call_command("loaddata", "alfenna/fixtures/catalog_courses.json", verbosity=0)
    logs.append("Fixtures catalog_courses.json chargées.")

    module = import_module("apps.atelier.compose.hydrators.course_detail.hydrators")
    ctx = module.sidebar(None, {"course_slug": "demo-course", "currency": "MAD"})

    required = ["price", "promotion", "currency", "course", "cta_guest_url", "cta_member_url"]
    for key in required:
        has_key = key in ctx and ctx[key] not in (None, "")
        logs.append(f"clé '{key}' présente: {has_key}")
        if not has_key:
            ok = False

    if ctx.get("currency") != "MAD":
        ok = False
        logs.append("Devrait renvoyer currency=MAD")

    if not isinstance(ctx.get("price"), int) or not isinstance(ctx.get("promotion"), int):
        ok = False
        logs.append("price/promotion devraient être des int")

    if ctx.get("promotion", 0) > ctx.get("price", 0):
        ok = False
        logs.append("Promotion ne doit pas dépasser le prix")

    login_url = getattr(settings, "LOGIN_URL", "")
    if login_url and "next=" not in ctx.get("cta_member_url", ""):
        ok = False
        logs.append("cta_member_url devrait contenir le paramètre next")

    duration = round(time.time() - started, 2)
    return {"ok": ok, "name": NAME, "duration": duration, "logs": logs}
