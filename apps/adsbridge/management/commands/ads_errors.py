"""Management command showing recent Google Ads conversion errors."""

from __future__ import annotations

from typing import Iterable

from django.core.management.base import BaseCommand

from apps.adsbridge.models import ConversionRecord


class Command(BaseCommand):
    help = "Affiche les dernieres conversions Google Ads en erreur avec details."

    def add_arguments(self, parser) -> None:  # pragma: no cover - argparser glue
        parser.add_argument(
            "--limit",
            type=int,
            default=10,
            help="Nombre maximum de conversions a afficher.",
        )
        parser.add_argument(
            "--status",
            choices=[choice for choice, _ in ConversionRecord.Status.choices],
            default=ConversionRecord.Status.ERROR,
            help="Filtre sur le statut (par défaut: ERROR).",
        )
        parser.add_argument(
            "--kind",
            choices=[choice for choice, _ in ConversionRecord.Kind.choices],
            default=None,
            help="Filtre optionnel sur le type de conversion.",
        )

    def handle(self, *args, **options) -> None:
        limit: int = options["limit"]
        status: str = options["status"]
        kind: str | None = options["kind"]

        queryset = ConversionRecord.objects.filter(status=status)
        if kind:
            queryset = queryset.filter(kind=kind)
        queryset = queryset.order_by("-updated_at")[:limit]

        records: Iterable[ConversionRecord] = queryset
        has_records = False
        for record in records:
            has_records = True
            payload = record.google_upload_status or {}
            code = payload.get("error_code") or "n/a"
            detail = payload.get("error_detail") or record.last_error or ""
            status_message = payload.get("status_message")
            line = (
                f"#{record.id} kind={record.kind} status={record.status} attempts={record.attempt_count} "
                f"code={code} detail={str(detail)[:240]}"
            )
            if status_message:
                line += f" status_message={str(status_message)[:160]}"
            self.stdout.write(line)
            errors = payload.get("errors") or []
            for err in errors:
                err_code = err.get("code") or "UNKNOWN"
                location = err.get("location") or "n/a"
                message = err.get("message") or ""
                self.stdout.write(f"  - {err_code} @ {location}: {message}")
            if not errors and record.last_error:
                self.stdout.write(f"  - last_error: {record.last_error}")

        if not has_records:
            self.stdout.write("Aucune conversion ne correspond aux filtres fournis.")
