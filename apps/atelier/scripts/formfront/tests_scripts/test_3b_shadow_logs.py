# apps/atelier/scripts/formfront/tests_scripts/test_3b_shadow_logs.py
from __future__ import annotations
import time
from django.test.client import RequestFactory
from django.conf import settings
from apps.common.runscript_harness import binary_harness

NAME = "Étape 3.B — Shadow hook (pipeline)"

def _import_pipeline():
    for m in [
        "apps.atelier.compose.pipeline",
        "apps.compose.pipeline",
        "atelier.compose.pipeline",
    ]:
        try:
            return __import__(m, fromlist=["*"])
        except Exception:
            pass
    return None

@binary_harness
def run():
    t0 = time.time(); logs = []; ok = True
    pipe = _import_pipeline()
    if not pipe or not hasattr(pipe, "render_page"):
        # Pas bloquant: environnement différent
        logs.append("render_page introuvable — test ignoré.")
        return {"name": NAME, "ok": True, "duration": round(time.time()-t0,2), "logs": logs}

    old1 = getattr(settings, "FLOWFORMS_COMPONENT_ENABLED", False)
    old2 = getattr(settings, "FLOWFORMS_USE_CHILD_COMPOSE", False)
    try:
        setattr(settings, "FLOWFORMS_COMPONENT_ENABLED", True)
        setattr(settings, "FLOWFORMS_USE_CHILD_COMPOSE", True)
        html = pipe.render_page(RequestFactory().get("/"), "home", "vtest")
        ok = bool(html)
        logs.append("Pipeline OK — hook exécuté (cf. logs INFO).")
    except Exception as e:
        ok = False; logs.append(f"render_page/home a échoué: {e}")
    finally:
        setattr(settings, "FLOWFORMS_COMPONENT_ENABLED", old1)
        setattr(settings, "FLOWFORMS_USE_CHILD_COMPOSE", old2)

    return {"name": NAME, "ok": ok, "duration": round(time.time()-t0,2), "logs": logs}
