from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, List

import django
from django.conf import settings
from django.core.management import call_command


def _ensure_setup() -> None:
    project_root = Path(__file__).resolve().parents[3]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "alfenna.settings.test_cli")
    if not settings.configured:
        django.setup()


def run() -> Dict[str, object]:
    _ensure_setup()

    results: Dict[str, object] = {"steps": []}
    ok = True

    try:
        call_command("check")
        results["steps"].append({"step": "check", "status": "ok"})
    except Exception as exc:  # pragma: no cover - fail fast path
        ok = False
        results["steps"].append({"step": "check", "status": "error", "error": str(exc)})

    if ok:
        try:
            call_command(
                "test",
                "apps.leads.tests.test_policy_optional",
                "apps.pages.tests.test_i18n_urls",
                "apps.atelier.tests.test_stepper_sync",
            )
            results["steps"].append({"step": "tests", "status": "ok"})
        except SystemExit as exc:  # pragma: no cover - Django test command exits with status
            ok = ok and exc.code == 0
            results["steps"].append({"step": "tests", "status": "error", "error": str(exc)})
        except Exception as exc:  # pragma: no cover
            ok = False
            results["steps"].append({"step": "tests", "status": "error", "error": str(exc)})

    script_suite = [
        "apps.leads.scripts.leads_00_urls",
        "apps.leads.scripts.leads_01_progress_create",
        "apps.leads.scripts.leads_02_progress_idem_merge",
        "apps.leads.scripts.leads_03_collect_online",
        "apps.leads.scripts.leads_04_collect_require_idem",
        "apps.leads.scripts.leads_05_policy_required",
        "apps.leads.scripts.leads_06_progress_error_log",
    ]

    if ok:
        for script in script_suite:
            try:
                call_command("runscript", script, "--traceback")
                results.setdefault("runscripts", []).append({"script": script, "status": "ok"})
            except SystemExit as exc:  # pragma: no cover - runscript returns via SystemExit
                success = exc.code == 0
                ok = ok and success
                results.setdefault("runscripts", []).append({
                    "script": script,
                    "status": "ok" if success else "error",
                    "exit_code": exc.code,
                })
            except Exception as exc:  # pragma: no cover
                ok = False
                results.setdefault("runscripts", []).append({
                    "script": script,
                    "status": "exception",
                    "error": str(exc),
                })

    results["ok"] = ok
    return results


if __name__ == "__main__":
    summary = run()
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if not summary.get("ok", False):
        raise SystemExit(1)
