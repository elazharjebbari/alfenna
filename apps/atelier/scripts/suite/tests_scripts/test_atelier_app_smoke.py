"""
Smoke test import modules atelier avec diagnostics.
Exécution: python manage.py runscript atelier_app_smoke
"""
import importlib
import importlib.util
import sys
from apps.common.runscript_harness import binary_harness

MODULES = [
    "apps.atelier",
    "apps.atelier.apps",
    "apps.atelier.admin",
    "apps.atelier.models",
    "apps.atelier.services",
    "apps.atelier.middleware",
    "apps.atelier.middleware.request_id",
    "apps.atelier.middleware.segments",
    "apps.atelier.middleware.vary",
    "apps.atelier.config",
    "apps.atelier.config.loader",
    "apps.atelier.config.schema",
    "apps.atelier.config.registry",
    "apps.atelier.ab",
    "apps.atelier.ab.waffle",
    "apps.atelier.ab.guard",
    "apps.atelier.components",
    "apps.atelier.components.registry",
    "apps.atelier.components.contracts",
    "apps.atelier.components.assets",
    "apps.atelier.components.metrics",
    "apps.atelier.components.templatetags",
    "apps.atelier.components.templatetags.atelier_components",
    "apps.atelier.compose",
    "apps.atelier.compose.pages",
    "apps.atelier.compose.pipeline",
    "apps.atelier.compose.cache",
    "apps.atelier.compose.hydration",
    "apps.atelier.compose.response",
    "apps.atelier.analytics",
    "apps.atelier.analytics.ingest",
    "apps.atelier.analytics.funnel",
    "apps.atelier.analytics.tasks",
    "apps.atelier.analytics.exporters",
]

@binary_harness
def run():
    print("=== atelier_app_smoke: START ===")
    print(f"sys.path[0]: {sys.path[0]}")
    ok = 0
    for module in MODULES:
        spec = importlib.util.find_spec(module)
        if spec is None:
            print(f"[MISS] {module} — introuvable dans sys.meta_path")
        else:
            origin = getattr(spec, 'origin', None)
            submodule_search_locations = getattr(spec, 'submodule_search_locations', None)
            if origin and origin != 'namespace':
                print(f"[FIND] {module} @ {origin}")
            elif submodule_search_locations:
                print(f"[FIND] {module} (package) @ {list(submodule_search_locations)}")
            try:
                importlib.import_module(module)
                print(f"[OK]   {module}")
                ok += 1
            except Exception as e:
                print(f"[ERR]  {module}: {e.__class__.__name__}: {e}")
    print(f"=== atelier_app_smoke: DONE ({ok}/{len(MODULES)} OK) ===")