"""Purge analytics raw events older than a configured threshold."""
from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.atelier.analytics.models import AnalyticsEventRaw


class Command(BaseCommand):
    help = "Purge analytics raw events older than the specified number of days."

    def add_arguments(self, parser):
        parser.add_argument(
            "--older-than",
            type=int,
            default=90,
            dest="older_than",
            help="Delete events older than N days (default: 90).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            dest="dry_run",
            help="Only report the number of rows that would be deleted.",
        )

    def handle(self, *args, **options):
        days = max(int(options["older_than"]), 0)
        dry_run = bool(options.get("dry_run"))
        cutoff = timezone.now() - timedelta(days=days)

        qs = AnalyticsEventRaw.objects.filter(ts__lt=cutoff)
        count = qs.count()
        if dry_run:
            self.stdout.write(self.style.WARNING(f"[dry-run] {count} events older than {days} days."))
            return

        deleted, _ = qs.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} analytics events older than {days} days."))
