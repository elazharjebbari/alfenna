from __future__ import annotations

from celery.exceptions import Retry
from django.core import mail
from django.test import TestCase, override_settings

from apps.messaging.models import EmailTemplate, OutboxEmail
from apps.messaging.services import EmailService
from apps.messaging.tasks import drain_outbox_batch, send_outbox_email


class MessagingTaskTests(TestCase):
    def setUp(self) -> None:
        EmailTemplate.objects.create(
            slug="tests/tasks-reset",
            locale="fr",
            version=1,
            subject="Reset",
            html_template="<p>Reset {{ code }}</p>",
            text_template="Reset {{ code }}",
        )

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_drain_triggers_delivery(self) -> None:
        outbox = EmailService.compose_and_enqueue(
            namespace="accounts",
            purpose="reset",
            template_slug="tests/tasks-reset",
            to=["user@example.com"],
            context={"code": "123456"},
        )

        drain_outbox_batch.apply(kwargs={"limit": 10}).get()

        outbox.refresh_from_db()
        self.assertEqual(outbox.status, OutboxEmail.Status.SENT)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(outbox.attempts.count(), 1)
        attempt = outbox.attempts.first()
        assert attempt is not None
        self.assertEqual(attempt.status, "success")

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_send_failure_requeues_message(self) -> None:
        outbox = EmailService.compose_and_enqueue(
            namespace="accounts",
            purpose="reset",
            template_slug="tests/tasks-reset",
            to=["user@example.com"],
            context={"code": "123456"},
        )

        # Force failure by patching send_messages
        from unittest import mock

        with mock.patch("apps.messaging.tasks.get_connection") as mocked_conn:
            mocked_conn.return_value.send_messages.side_effect = RuntimeError("smtp down")
            with self.assertRaises(Retry):
                send_outbox_email.apply(args=[outbox.id]).get()

        outbox.refresh_from_db()
        self.assertEqual(outbox.status, OutboxEmail.Status.QUEUED)
        self.assertEqual(outbox.attempt_count, 1)
        self.assertEqual(outbox.attempts.count(), 1)
        self.assertIn("smtp down", outbox.last_error_message)
