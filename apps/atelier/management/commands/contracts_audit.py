# apps/atelier/management/commands/contracts_audit.py
from __future__ import annotations
import sys
from typing import Optional
from django.core.management.base import BaseCommand, CommandParser

from apps.atelier.reports.contracts_audit import run_audit


class Command(BaseCommand):
    help = "Audite les contrats des composants (hydrate + validate) et produit un rapport Markdown + JSONL."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--outdir", type=str, default="reports/contracts", help="Dossier de sortie des rapports")
        parser.add_argument("--env", type=str, default=None, help="Nom d'environnement (ex: dev|staging|prod)")
        parser.add_argument("--content-rev", type=str, default=None, help="content_rev à logger (optionnel)")
        parser.add_argument("--git-sha", type=str, default=None, help="SHA du commit (optionnel)")
        parser.add_argument("--strict-warn", action="store_true", help="Fait échouer si WARN > 0")
        parser.add_argument("--quiet", action="store_true", help="Sortie console minimale")

    def handle(self, *args, **options):
        outdir: str = options["outdir"]
        env: Optional[str] = options.get("env")
        content_rev: Optional[str] = options.get("content_rev")
        git_sha: Optional[str] = options.get("git_sha")
        strict_warn: bool = options.get("strict_warn", False)
        quiet: bool = options.get("quiet", False)

        summary, _ = run_audit(outdir=outdir, env=env, content_rev=content_rev, git_sha=git_sha)

        if not quiet:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("=== Contrats — Résumé ==="))
            self.stdout.write(f"Checks: {summary.total_checks} | OK: {summary.ok} | WARN: {summary.warn} | ERROR: {summary.error}")
            self.stdout.write(f"Rapports: {outdir}/<timestamp>_report.md  et  {outdir}/<timestamp>_stream.jsonl")
            self.stdout.write("")

        # Exit codes pour CI
        if summary.error > 0:
            sys.exit(2)
        if strict_warn and summary.warn > 0:
            sys.exit(1)
        sys.exit(0)
