from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, List

import django
from django.conf import settings
from django.core.management import call_command
from django.test import Client
from django.utils import translation
from django.utils.translation import gettext as _


def _ensure_setup() -> None:
    project_root = Path(__file__).resolve().parents[3]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "alfenna.settings.dev")
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

    if ok:
        client = Client()
        crawl: List[Dict[str, object]] = []
        expectations = {
            "fr": "NATUREL • SOIN • CONFIANCE",
            "en": "NATURAL • CARE • TRUST",
            "ar": "طبيعي • عناية • ثقة",
        }
        for lang, expected in expectations.items():
            response = client.get(f"/{lang}/")
            entry = {
                "lang": lang,
                "status": response.status_code,
                "content_language": response.headers.get("Content-Language"),
            }

            entry_ok = response.status_code == 200 and entry["content_language"] == lang
            with translation.override(lang):
                entry["translation"] = _("NATUREL • SOIN • CONFIANCE")
                entry_ok = entry_ok and entry["translation"] == expected

            entry["ok"] = entry_ok
            ok = ok and entry_ok
            crawl.append(entry)
        results["crawl"] = crawl

    results["ok"] = ok
    return results


if __name__ == "__main__":
    summary = run()
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if not summary.get("ok", False):
        raise SystemExit(1)
