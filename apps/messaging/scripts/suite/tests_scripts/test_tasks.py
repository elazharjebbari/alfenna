from __future__ import annotations

import uuid

from django.core import mail
from django.test.utils import override_settings

from apps.messaging.models import EmailTemplate, OutboxEmail
from apps.messaging.services import EmailService
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def run():
    template, _ = EmailTemplate.objects.get_or_create(
        slug="scripts/diagnostic",
        locale="fr",
        defaults={
            "version": 1,
            "subject": "Diagnostic",
            "html_template": "<p>Diagnostic</p>",
            "text_template": "Diagnostic",
        },
    )

    dedup_key = f"diagnostic-{uuid.uuid4()}"
    outbox = EmailService.compose_and_enqueue(
        namespace="scripts",
        purpose="diagnostic",
        template_slug=template.slug,
        to=["diagnostic@example.com"],
        dedup_key=dedup_key,
    )

    outbox.refresh_from_db()
    success = outbox.status == OutboxEmail.Status.SENT
    attempts = outbox.attempts.count()
    mails_sent = len(mail.outbox)

    return {
        "ok": success and attempts == 1 and mails_sent == 1,
        "name": "test_tasks",
        "duration": 0.0,
        "logs": [
            f"status={outbox.status}",
            f"attempts={attempts}",
            f"mailbox={mails_sent}",
        ],
    }
