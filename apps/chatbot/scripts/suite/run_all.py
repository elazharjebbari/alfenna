"""Run all chatbot script checks.

Usage:
    python manage.py runscript apps.chatbot.scripts.suite.run_all
"""
from __future__ import annotations

import importlib
import pkgutil
import time


ANSI = {"G": "\033[92m", "R": "\033[91m", "B": "\033[94m", "X": "\033[0m"}


def run() -> None:
    start = time.time()
    package = __name__.rsplit(".", 1)[0] + ".tests_scripts"
    module = importlib.import_module(package)
    results = []

    for _, mod_name, _ in pkgutil.iter_modules(module.__path__):
        if not mod_name.startswith("test_"):
            continue
        print(f"→ Running {mod_name}")
        mod = importlib.import_module(f"{package}.{mod_name}")
        if hasattr(mod, "run"):
            result = mod.run()
        else:
            result = None
        results.append(bool(result) if result is not None else True)

    ok = sum(1 for value in results if value)
    total = len(results)
    duration = round(time.time() - start, 2)
    color = "G" if ok == total else "R"
    print(f"{ANSI[color]}Terminé: {ok}/{total} OK en {duration}s{ANSI['X']}")
