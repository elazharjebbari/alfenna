"""Release held conversion records for processing."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.adsbridge import conf as ads_conf
from apps.adsbridge.models import ConversionRecord
from apps.adsbridge import tasks


class Command(BaseCommand):
    help = "Requeue Google Ads conversions currently HELD."  # noqa: A003 - django expects attribute

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--all",
            action="store_true",
            help="Release all HELD records.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of records to release (requires --all).",
        )

    def handle(self, *args, **options):
        mode = ads_conf.current_mode()
        if mode not in {"on", "mock"}:
            self.stderr.write(
                "Cannot release held records while ADS_S2S_MODE is '%s'." % mode
            )
            raise SystemExit(2)

        if not options.get("all"):
            self.stderr.write("Specify --all to release held records.")
            raise SystemExit(2)

        queryset = ConversionRecord.objects.filter(status=ConversionRecord.Status.HELD).order_by(
            "created_at"
        )
        limit = options.get("limit")
        if limit:
            queryset = queryset[:limit]

        ids = list(queryset.values_list("id", flat=True))
        if not ids:
            self.stdout.write("No held records to release.")
            return

        updated = 0
        for record_id in ids:
            record = ConversionRecord.objects.get(id=record_id)
            record.status = ConversionRecord.Status.PENDING
            record.hold_reason = ""
            record.effective_mode = mode
            record.save(update_fields=["status", "hold_reason", "effective_mode", "updated_at"])
            tasks.enqueue_conversion(record.id)
            updated += 1

        self.stdout.write(f"Released {updated} held conversion record(s)")
