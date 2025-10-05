from __future__ import annotations

from celery.exceptions import Retry
from django.test import TestCase, override_settings
from django.utils import timezone
from smtplib import SMTPRecipientsRefused
from unittest.mock import patch

from apps.messaging.models import OutboxEmail, EmailAttempt
from apps.messaging.tasks import send_outbox_email


class SendOutboxEmailRetryTests(TestCase):
    def setUp(self) -> None:
        OutboxEmail.objects.all().delete()
        EmailAttempt.objects.all().delete()

    @override_settings(PASSWORD_RESET_MAX_ATTEMPTS=5, PASSWORD_RESET_RETRY_INTERVAL_SECONDS=300)
    def test_bounce_limit_schedules_retry_with_eta(self) -> None:
        outbox = OutboxEmail.objects.create(
            namespace="accounts",
            purpose="password_reset",
            flow_id="flow-bounce",
            dedup_key="bounce",
            to=["cli-reset@example.com"],
            template_slug="accounts/reset",
            template_version=1,
            rendered_subject="subject",
            rendered_text="body",
            rendered_html="<p>body</p>",
            status=OutboxEmail.Status.QUEUED,
        )

        class FailingConn:
            def send_messages(self, messages):  # pragma: no cover - exercised via task
                raise SMTPRecipientsRefused(
                    {"cli-reset@example.com": (550, b"5.4.6 Sender Hourly Bounce Limit Exceeded - repro")}
                )

        with patch("apps.messaging.tasks.get_connection", return_value=FailingConn()):
            with self.assertRaises(Retry):
                send_outbox_email.apply(args=[outbox.id])

        outbox.refresh_from_db()
        self.assertEqual(outbox.status, OutboxEmail.Status.RETRYING)
        self.assertEqual(outbox.last_error_code, "bounce_limit")
        self.assertGreater(outbox.attempt_count, 0)
        self.assertIsNotNone(outbox.next_attempt_at)
        delta = outbox.next_attempt_at - timezone.now()
        self.assertTrue(280 <= delta.total_seconds() <= 320)
        attempt = EmailAttempt.objects.filter(outbox=outbox).latest("created_at")
        self.assertEqual(attempt.status, EmailAttempt.Status.FAILURE)

    @override_settings(PASSWORD_RESET_MAX_ATTEMPTS=3, PASSWORD_RESET_RETRY_INTERVAL_SECONDS=120)
    def test_retry_limit_marks_suppressed(self) -> None:
        outbox = OutboxEmail.objects.create(
            namespace="accounts",
            purpose="password_reset",
            flow_id="flow-final",
            dedup_key="final",
            to=["cli-reset@example.com"],
            template_slug="accounts/reset",
            template_version=1,
            rendered_subject="subject",
            rendered_text="body",
            rendered_html="<p>body</p>",
            status=OutboxEmail.Status.QUEUED,
            attempt_count=2,
        )

        class FailingConn:
            def send_messages(self, messages):  # pragma: no cover - exercised via task
                raise SMTPRecipientsRefused({"cli-reset@example.com": (550, b"5.4.6 Sender Hourly Bounce Limit Exceeded")})

        # After increment inside the task, attempt_count will reach 3 (max), triggering terminal path.
        with patch("apps.messaging.tasks.get_connection", return_value=FailingConn()):
            send_outbox_email.apply(args=[outbox.id])

        outbox.refresh_from_db()
        self.assertEqual(outbox.status, OutboxEmail.Status.SUPPRESSED)
        self.assertEqual(outbox.last_error_code, "bounce_limit")
        self.assertIsNone(outbox.next_attempt_at)
        attempt = EmailAttempt.objects.filter(outbox=outbox).latest("created_at")
        self.assertEqual(attempt.status, EmailAttempt.Status.FAILURE)

    @override_settings(PASSWORD_RESET_MAX_ATTEMPTS=5, PASSWORD_RESET_RETRY_INTERVAL_SECONDS=300)
    def test_recipient_unknown_is_terminal_without_retry(self) -> None:
        outbox = OutboxEmail.objects.create(
            namespace="accounts",
            purpose="password_reset",
            flow_id="flow-recipient",
            dedup_key="recipient",
            to=["cli-invalid@example.com"],
            template_slug="accounts/reset",
            template_version=1,
            rendered_subject="subject",
            rendered_text="body",
            rendered_html="<p>body</p>",
            status=OutboxEmail.Status.QUEUED,
        )

        class InvalidConn:
            def send_messages(self, messages):  # pragma: no cover - exercised via task
                raise SMTPRecipientsRefused({
                    "cli-invalid@example.com": (550, b"5.1.1 User unknown")
                })

        with patch("apps.messaging.tasks.get_connection", return_value=InvalidConn()):
            send_outbox_email.apply(args=[outbox.id])

        outbox.refresh_from_db()
        self.assertEqual(outbox.status, OutboxEmail.Status.SUPPRESSED)
        self.assertEqual(outbox.last_error_code, "recipient_unknown")
        self.assertEqual(outbox.attempt_count, 1)
        self.assertIsNone(outbox.next_attempt_at)
        attempt = EmailAttempt.objects.filter(outbox=outbox).latest("created_at")
        self.assertEqual(attempt.status, EmailAttempt.Status.FAILURE)
