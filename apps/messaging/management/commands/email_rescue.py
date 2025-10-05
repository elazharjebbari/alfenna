from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.messaging.models import OutboxEmail
from apps.messaging.tasks import drain_outbox_batch


class Command(BaseCommand):
    help = "Réinitialise les Outbox bloquées en SENDING et relance un drain."

    def handle(self, *args, **options) -> None:
        cutoff = timezone.now() - timedelta(minutes=5)
        stuck = OutboxEmail.objects.filter(
            status=OutboxEmail.Status.SENDING,
            updated_at__lt=cutoff,
        )
        count = stuck.update(status=OutboxEmail.Status.QUEUED, retry_at=None)
        self.stdout.write(f"Réinitialisées: {count}")
        drain_outbox_batch(limit=50)
        self.stdout.write("Drain relancé.")
