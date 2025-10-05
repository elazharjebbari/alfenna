from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

from apps.chatbot.tasks import purge_chat_messages_older_than

log = logging.getLogger("chatbot.service")


class Command(BaseCommand):
    help = "Purge chatbot messages older than the retention policy."

    def add_arguments(self, parser):  # type: ignore[override]
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="Override CHATBOT_RETENTION_DAYS for this purge run.",
        )

    def handle(self, *args, **options):  # type: ignore[override]
        days = options.get("days")
        deleted = purge_chat_messages_older_than(days)
        log.info("chatbot_purge_completed", extra={"deleted": deleted, "override_days": days})
        self.stdout.write(self.style.SUCCESS(f"Purged {deleted} messages"))
