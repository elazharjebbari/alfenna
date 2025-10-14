import importlib
import time
from typing import Dict, List

SCRIPTS = [
    "apps.pages.scripts.smoke_product_page",
    "apps.atelier.scripts.components.fab_whatsapp_smoke",
    "apps.atelier.scripts.suite.tests_scripts.test_lang_prefix_smoke",
    "apps.atelier.scripts.suite.tests_scripts.test_rtl_layout_smoke",
    "apps.atelier.scripts.suite.tests_scripts.test_i18n_walk_smoke",
]


def run() -> Dict[str, object]:
    started = time.time()
    results: List[Dict[str, object]] = []
    for dotted in SCRIPTS:
        module = importlib.import_module(dotted)
        result = module.run()
        results.append(result)
        status = "OK" if result.get("ok") else "FAIL"
        print(f"[{status}] {result.get('name')} — {result.get('logs')}")
    duration = round(time.time() - started, 3)
    ok_count = sum(1 for item in results if item.get("ok"))
    print(f"Summary: {ok_count}/{len(results)} OK, total={duration}s")
    return {
        "ok": ok_count == len(results),
        "name": "run_all",
        "duration": duration,
        "logs": results,
    }
