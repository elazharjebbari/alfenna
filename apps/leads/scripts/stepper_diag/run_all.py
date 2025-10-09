from __future__ import annotations

import importlib
import json
import pkgutil
import time
from pathlib import Path


def _iter_test_modules():
    base = Path(__file__).resolve().parent / "tests_scripts"
    for module in sorted(pkgutil.iter_modules([str(base)]), key=lambda item: item.name):
        if module.name.startswith("test_"):
            yield module.name


def run():  # pragma: no cover - executed via runscript
    started = time.time()
    results = []
    ok = True

    for module_name in _iter_test_modules():
        module = importlib.import_module(
            f"apps.leads.scripts.stepper_diag.tests_scripts.{module_name}"
        )
        result = module.run()
        results.append({"module": module_name, **result})
        ok = ok and result.get("ok", False)

    summary = {
        "ok": ok,
        "duration": round(time.time() - started, 3),
        "results": results,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


if __name__ == "__main__":  # pragma: no cover - manual execution
    outcome = run()
    if not outcome.get("ok", False):
        raise SystemExit(1)
