import importlib
import time
import traceback
import pkgutil

PKG = "apps.atelier.scripts.analytics.product_detail.tests_scripts"


def _iter_tests():
    pkg = importlib.import_module(PKG)
    for info in pkgutil.iter_modules(pkg.__path__):
        if info.name.startswith("test_"):
            yield f"{PKG}.{info.name}"


def run():
    started = time.time()
    results = []
    for dotted in sorted(_iter_tests()):
        try:
            mod = importlib.import_module(dotted)
            res = mod.run()
            results.append(res)
            status = "OK" if res.get("ok") else "FAIL"
            print(f"[{status}] {res.get('name')} ({res.get('duration')}s) — {res.get('logs')}")
        except Exception as exc:  # pragma: no cover — diagnostic path
            tb = traceback.format_exc(limit=2)
            print(f"[EXC] {dotted}: {exc}\n{tb}")
            results.append({
                "ok": False,
                "name": dotted,
                "duration": 0,
                "logs": str(exc),
            })
    ok_count = sum(1 for item in results if item.get("ok"))
    total = len(results)
    duration = round(time.time() - started, 3)
    print(f"\nSummary: {ok_count}/{total} OK, total={duration}s")
    return {
        "ok": ok_count == total,
        "name": "run_all",
        "duration": duration,
        "logs": "",
    }
