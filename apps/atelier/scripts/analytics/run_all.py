"""Run all analytics validation scripts.

Usage:
    python manage.py runscript apps.atelier.scripts.analytics.run_all
"""
from __future__ import annotations

import importlib
import pkgutil
import time


def run():
    start = time.time()
    package = __name__.rsplit('.', 1)[0] + '.tests_scripts'
    results = []
    for _, modname, _ in pkgutil.iter_modules(importlib.import_module(package).__path__):
        if not modname.startswith('test_'):
            continue
        module = importlib.import_module(f'{package}.{modname}')
        if hasattr(module, 'run'):
            print(f'→ Running {modname}')
            res = module.run()
            if not isinstance(res, dict):
                res = {"ok": bool(res), "name": modname, "duration": 0.0, "logs": []}
            results.append(res)
    ok = sum(1 for r in results if r.get('ok'))
    print(f'Terminé: {ok}/{len(results)} OK en {round(time.time() - start, 2)}s')
    return results
