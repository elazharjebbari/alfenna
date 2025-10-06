from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db.models import Avg, Count, Q

from apps.chatbot.metrics import snapshot
from apps.chatbot.models import ChatMessage, ChatSession, ProviderCall


class Command(BaseCommand):
    help = "Export aggregated chatbot metrics."

    def handle(self, *args, **options):  # type: ignore[override]
        session_total = ChatSession.objects.count()
        active_sessions = ChatSession.objects.filter(closed_at__isnull=True).count()
        messages_total = ChatMessage.objects.count()
        message_breakdown = ChatMessage.objects.values("role").annotate(total=Count("id"))
        provider_stats = ProviderCall.objects.aggregate(
            total=Count("id"),
            success=Count("id", filter=Q(status=ProviderCall.STATUS_SUCCESS)),
            error=Count("id", filter=Q(status=ProviderCall.STATUS_ERROR)),
            avg_duration=Avg("duration_ms"),
        )

        metrics_cache = snapshot()

        self.stdout.write("Chatbot metrics summary:\n")
        self.stdout.write(f"  Sessions total       : {session_total}")
        self.stdout.write(f"  Sessions active      : {active_sessions}")
        self.stdout.write(f"  Messages total       : {messages_total}")
        for entry in message_breakdown:
            self.stdout.write(f"    - {entry['role']}: {entry['total']}")
        self.stdout.write("\n  Provider calls:")
        self.stdout.write(
            f"    total={provider_stats['total'] or 0}, "
            f"success={provider_stats['success'] or 0}, "
            f"error={provider_stats['error'] or 0}, "
            f"avg_duration_ms={round(provider_stats['avg_duration'] or 0, 2)}"
        )
        self.stdout.write("\n  Cache snapshot:")
        for key, value in metrics_cache.items():
            self.stdout.write(f"    {key}: {value}")
        self.stdout.write("\nDone.")
