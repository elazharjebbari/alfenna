"""Run all product_detail analytics validation scripts."""
from __future__ import annotations

import importlib
import pkgutil
import time

PACKAGE = "apps.atelier.scripts.analytics.product_detail.tests_scripts"


def run():
    start = time.time()
    results = []
    package = importlib.import_module(PACKAGE)
    names = sorted(
        modname for _, modname, _ in pkgutil.iter_modules(package.__path__) if modname.startswith("test_")
    )
    for modname in names:
        module = importlib.import_module(f"{PACKAGE}.{modname}")
        if hasattr(module, "run"):
            print(f"→ Running {modname}")
            res = module.run()
            if not isinstance(res, dict):
                res = {"ok": bool(res), "name": modname, "duration": 0.0, "logs": []}
            results.append(res)
    duration = round(time.time() - start, 2)
    ok_count = sum(1 for r in results if r.get("ok"))
    print(f"Terminé: {ok_count}/{len(results)} OK en {duration}s")
    return results
