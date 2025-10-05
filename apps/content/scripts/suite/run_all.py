"""
Run all content scripts suite tests:
  python manage.py runscript apps.content.scripts.suite.run_all
"""
from __future__ import annotations

import importlib
import pkgutil
import time

ANSI = {"G": "\033[92m", "R": "\033[91m", "X": "\033[0m"}


def run():  # pragma: no cover
    started = time.time()
    package = __name__.rsplit(".", 1)[0] + ".tests_scripts"
    results = []
    for _, modname, _ in pkgutil.iter_modules(importlib.import_module(package).__path__):
        if not modname.startswith("test_"):
            continue
        module = importlib.import_module(f"{package}.{modname}")
        if hasattr(module, "run"):
            print(f"→ Running {modname}")
            res = module.run()
            if not isinstance(res, dict):
                res = {"ok": bool(res), "name": modname, "duration": 0.0, "logs": []}
            results.append(res)
    ok = sum(1 for res in results if res.get("ok"))
    total = len(results)
    print(f"Terminé: {ANSI['G']}{ok}{ANSI['X']}/{total} OK en {time.time() - started:.2f}s")
    return {"ok": ok == total, "name": "run_all", "duration": time.time() - started, "logs": results}
