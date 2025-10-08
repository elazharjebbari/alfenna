"""Run all product_detail analytics checks."""
from __future__ import annotations

import importlib
import pkgutil
import time

from apps.common.runscript_harness import binary_harness


@binary_harness
def run():
    started = time.time()
    package = __name__.rsplit('.', 1)[0] + '.tests_scripts'
    modules = importlib.import_module(package)
    results = []
    for _, modname, _ in pkgutil.iter_modules(modules.__path__):
        if not modname.startswith('test_'):
            continue
        module = importlib.import_module(f'{package}.{modname}')
        if hasattr(module, 'run'):
            print(f'→ Running {modname}')
            res = module.run()
            if not isinstance(res, dict):
                res = {"ok": bool(res), "name": modname, "duration": 0.0, "logs": []}
            results.append(res)
    ok_tests = sum(1 for res in results if res.get('ok'))
    total = len(results)
    duration = time.time() - started
    print(f'Terminé: {ok_tests}/{total} OK en {duration:.2f}s')
    return {
        "ok": ok_tests == total,
        "name": "pd_run_all",
        "duration": duration,
        "logs": [f"{res.get('name')}: {'OK' if res.get('ok') else 'KO'}" for res in results],
    }
