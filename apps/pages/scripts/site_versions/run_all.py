"""Exécution:
  python manage.py runscript apps.pages.scripts.site_versions.run_all
"""
from __future__ import annotations

import importlib
import pkgutil
import time


def run():
    start = time.time()
    base_package = __name__.rsplit(".", 1)[0]
    package = base_package + ".tests_scripts"
    tests_pkg = importlib.import_module(package)

    results = []
    for _, module_name, _ in pkgutil.iter_modules(tests_pkg.__path__):
        if not module_name.startswith("test_"):
            continue
        module = importlib.import_module(f"{package}.{module_name}")
        if hasattr(module, "run"):
            print(f"→ Running {module_name}")
            result = module.run()
            if not isinstance(result, dict):
                result = {"ok": bool(result), "name": module_name, "duration": 0.0, "logs": []}
            results.append(result)

    ok_count = sum(1 for res in results if res.get("ok"))
    total = len(results)
    duration = round(time.time() - start, 2)
    print(f"Terminé: {ok_count}/{total} OK en {duration}s")
    for res in results:
        status = "OK" if res.get("ok") else "FAIL"
        print(f" - {status} | {res.get('name')} | {res.get('duration')}s")
        for log_line in res.get("logs", []) or []:
            print(f"    {log_line}")
