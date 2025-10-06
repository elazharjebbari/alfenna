# apps/atelier/scripts/formfront/tests_scripts/test_3a_shadow_parity.py
from __future__ import annotations
import time
from django.test.client import RequestFactory
from django.conf import settings
from apps.atelier.components.forms.shell.hydrators import hydrate as shell_hydrate
from apps.atelier.components.forms.shell.parity import check_parity
from apps.common.runscript_harness import binary_harness

NAME = "Étape 3.A — Shadow parity (compose vs legacy)"

@binary_harness
def run():
    t0 = time.time(); logs = []; ok = True
    # Force compose ON
    old1 = getattr(settings, "FLOWFORMS_COMPONENT_ENABLED", False)
    old2 = getattr(settings, "FLOWFORMS_USE_CHILD_COMPOSE", False)
    try:
        setattr(settings, "FLOWFORMS_COMPONENT_ENABLED", True)
        setattr(settings, "FLOWFORMS_USE_CHILD_COMPOSE", True)

        req = RequestFactory().get("/")
        ctx = shell_hydrate(req, params={"title_html": "Titre test"})
        keys = sorted(list(ctx.keys()))
        logs.append(f"Hydrate keys: {keys}")

        if "children" not in ctx:
            ok = False; logs.append("❌ compose ON: ctx.children manquant")
        if "__shadow_legacy" not in ctx:
            ok = False; logs.append("❌ compose ON: ctx.__shadow_legacy manquant")

        if ok:
            html_compose = ctx["children"]["wizard"]
            html_legacy = ctx["__shadow_legacy"]["wizard_html"]
            res = check_parity(html_compose, html_legacy)
            logs.append(f"Parity result: ok={res['ok']} details={res['details']}")
            if not res["ok"]:
                ok = False
    finally:
        setattr(settings, "FLOWFORMS_COMPONENT_ENABLED", old1)
        setattr(settings, "FLOWFORMS_USE_CHILD_COMPOSE", old2)

    return {"name": NAME, "ok": ok, "duration": round(time.time()-t0,2), "logs": logs}
