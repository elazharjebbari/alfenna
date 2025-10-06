# apps/atelier/scripts/phase6/contracts_audit.py
from __future__ import annotations
from apps.atelier.reports.contracts_audit import run_audit
from apps.common.runscript_harness import binary_harness

@binary_harness
def run():
    summary, _ = run_audit(outdir="reports/contracts")
    print("\n=== Contrats — Résumé (runscript) ===")
    print(f"Checks: {summary.total_checks} | OK: {summary.ok} | WARN: {summary.warn} | ERROR: {summary.error}")
    print("Voir: reports/contracts/<timestamp>_report.md  et  _stream.jsonl\n")
