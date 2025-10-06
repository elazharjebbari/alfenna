"""
Discover and execute all bundle run_all scripts, producing a markdown report
similar to tools/run_all_bundles.sh while printing a summary table.
Usage:
  DJANGO_SETTINGS_MODULE=alfenna.settings.test_cli \
  python manage.py runscript scripts.run_all_discover
"""
from __future__ import annotations

import io
import os
import time
import traceback
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Tuple

import django
from django.apps import apps as django_apps
from django.core.management import call_command

BASE_DIR = Path(__file__).resolve().parent.parent
APPS_DIR = BASE_DIR / "apps"


def _iter_run_all_modules() -> List[str]:
    modules: List[str] = []
    for path in sorted(APPS_DIR.rglob("run_all.py")):
        if "migrations" in path.parts or "tests" in path.parts:
            continue
        if "scripts" not in path.parts:
            continue
        scripts_idx = path.parts.index("scripts")
        # Require a bundle directory after "scripts"
        if scripts_idx >= len(path.parts) - 2:
            continue
        module = ".".join(path.relative_to(BASE_DIR).with_suffix("").parts)
        modules.append(module)
    return modules


def _write_report(report_path: Path, rows: Iterable[Tuple[str, str, int, Path]], timestamp: str) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Bundles run_all — {timestamp}",
        "",
        f"- Conda env: `{os.environ.get('CONDA_DEFAULT_ENV', 'n/a')}`",
        f"- DJANGO_SETTINGS_MODULE: `{os.environ.get('DJANGO_SETTINGS_MODULE', 'n/a')}`",
        "",
        "| Bundle | Status | Duration (s) | Log |",
        "|---|---|---:|---|",
    ]
    for module, status, duration, rel_log in rows:
        lines.append(
            f"| `{module}` | {status} | {duration} | [log]({rel_log.as_posix()}) |"
        )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _print_table(rows: Iterable[Tuple[str, str, int, Path]]) -> None:
    data = list(rows)
    if not data:
        print("No run_all bundles found.")
        return
    headers = ("Bundle", "Status", "Duration (s)", "Log")
    widths = [len(h) for h in headers]
    for module, status, duration, rel_log in data:
        widths[0] = max(widths[0], len(module))
        widths[1] = max(widths[1], len(status))
        widths[2] = max(widths[2], len(str(duration)))
        widths[3] = max(widths[3], len(rel_log.as_posix()))

    def fmt_row(values: Iterable[str]) -> str:
        return " | ".join(
            str(value).ljust(width)
            for value, width in zip(values, widths)
        )

    separator = "-+-".join("-" * width for width in widths)
    print(fmt_row(headers))
    print(separator)
    for module, status, duration, rel_log in data:
        print(fmt_row((module, status, duration, rel_log.as_posix())))


def run() -> None:
    if not django_apps.ready:
        django.setup()
    modules = _iter_run_all_modules()
    if not modules:
        print("Aucun bundle run_all détecté.")
        return
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    report_dir = BASE_DIR / "reports"
    log_dir = report_dir / f"bundles_logs_{timestamp}"
    log_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"bundles_report_{timestamp}.md"

    results: List[Tuple[str, str, int, Path]] = []

    for module in modules:
        log_path = log_dir / f"{module.replace('.', '_')}.log"
        start = time.time()
        buffer = io.StringIO()
        status = "PASS"
        try:
            with redirect_stdout(buffer), redirect_stderr(buffer):
                call_command("runscript", module)
        except Exception:
            status = "FAIL"
            buffer.write("\n" + traceback.format_exc())
        duration = int(time.time() - start)
        output = buffer.getvalue()
        if status == "PASS" and ("RESULT:KO" in output or "ECHEC" in output):
            status = "FAIL"
        log_path.write_text(output, encoding="utf-8")
        rel_log = log_path.relative_to(BASE_DIR)
        results.append((module, status, duration, rel_log))

    _write_report(report_path, results, timestamp)
    _print_table(results)
    print(f"\nReport written to: {report_path.relative_to(BASE_DIR)}")


if __name__ == "__main__":  # pragma: no cover
    run()
