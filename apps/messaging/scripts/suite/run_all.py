"""Runs all messaging diagnostic scripts with a compact summary output."""
from __future__ import annotations

import importlib
import pkgutil
import time
from dataclasses import dataclass
from typing import Iterable, List

ANSI = {"G": "\033[92m", "R": "\033[91m", "Y": "\033[93m", "X": "\033[0m"}


@dataclass
class ScriptResult:
    name: str
    ok: bool
    duration: float
    logs: List[str]


def _iter_scripts(package: str) -> Iterable[str]:
    module = importlib.import_module(package)
    for _, modname, _ in pkgutil.iter_modules(module.__path__):  # type: ignore[arg-type]
        if modname.startswith("test_"):
            yield f"{package}.{modname}"


def _execute(module_path: str) -> ScriptResult:
    started = time.time()
    module = importlib.import_module(module_path)
    result = module.run() if hasattr(module, "run") else None
    duration = time.time() - started

    if isinstance(result, dict):
        ok = bool(result.get("ok"))
        logs = list(result.get("logs", []))
    else:
        ok = bool(result)
        logs = []
    return ScriptResult(name=module_path.rsplit(".", 1)[-1], ok=ok, duration=duration, logs=logs)


def run() -> None:
    started = time.time()
    package = __name__.rsplit(".", 1)[0] + ".tests_scripts"
    results = [
        _execute(module)
        for module in _iter_scripts(package)
    ]
    successes = sum(1 for res in results if res.ok)
    total = len(results)

    print("\nMessaging run_all summary:\n")
    for res in results:
        status = f"{ANSI['G']}PASS{ANSI['X']}" if res.ok else f"{ANSI['R']}FAIL{ANSI['X']}"
        print(f" - {res.name:<24} {status} {res.duration:.2f}s")
        for line in res.logs:
            print(f"   ↳ {line}")

    elapsed = time.time() - started
    palette = ANSI['G'] if successes == total else ANSI['Y'] if successes else ANSI['R']
    print(f"\nTotal: {successes}/{total} scripts ok (elapsed {elapsed:.2f}s)")
    print(ANSI['X'], end="")


if __name__ == "__main__":
    run()
