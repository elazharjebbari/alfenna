from __future__ import annotations

from uuid import uuid4

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.views import (
    PASSWORD_RESET_FLOWS_SESSION_KEY,
    PASSWORD_RESET_LAST_FLOW_KEY,
)
from apps.messaging.models import OutboxEmail


class PasswordResetStatusViewTests(TestCase):
    def setUp(self) -> None:
        OutboxEmail.objects.all().delete()

    def _prime_session(self, flow_id: str, state: str = "queued") -> None:
        session = self.client.session
        session[PASSWORD_RESET_FLOWS_SESSION_KEY] = {
            flow_id: {"flow_id": flow_id, "state": state, "created_at": timezone.now().isoformat()}
        }
        session[PASSWORD_RESET_LAST_FLOW_KEY] = flow_id
        session.save()

    @override_settings(PASSWORD_RESET_MAX_ATTEMPTS=5)
    def test_status_endpoint_no_outbox_returns_noop(self) -> None:
        flow_id = uuid4().hex
        self._prime_session(flow_id, state="noop")

        response = self.client.get(reverse("accounts:password_reset_status", args=[flow_id]))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["flow_id"], flow_id)
        self.assertEqual(payload["state"], "noop")
        self.assertEqual(payload["attempt_count"], 0)

    @override_settings(PASSWORD_RESET_MAX_ATTEMPTS=5)
    def test_status_endpoint_reports_retrying_state(self) -> None:
        flow_id = uuid4().hex
        self._prime_session(flow_id)
        eta = timezone.now() + timezone.timedelta(minutes=5)
        OutboxEmail.objects.create(
            namespace="accounts",
            purpose="password_reset",
            flow_id=flow_id,
            dedup_key="status-test",
            to=["cli@example.com"],
            template_slug="accounts/reset",
            template_version=1,
            rendered_subject="s",
            rendered_text="t",
            rendered_html="<p>t</p>",
            status=OutboxEmail.Status.RETRYING,
            attempt_count=2,
            next_attempt_at=eta,
            scheduled_at=eta,
            last_error_code="bounce_limit",
        )

        response = self.client.get(reverse("accounts:password_reset_status", args=[flow_id]))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["state"], "retrying")
        self.assertEqual(payload["attempt_count"], 2)
        self.assertEqual(payload["issue_code"], "bounce_limit")
        self.assertIsNotNone(payload["next_attempt_eta"])

    @override_settings(PASSWORD_RESET_MAX_ATTEMPTS=5)
    def test_status_endpoint_clears_session_after_sent(self) -> None:
        flow_id = uuid4().hex
        self._prime_session(flow_id)
        OutboxEmail.objects.create(
            namespace="accounts",
            purpose="password_reset",
            flow_id=flow_id,
            dedup_key="status-sent",
            to=["cli@example.com"],
            template_slug="accounts/reset",
            template_version=1,
            rendered_subject="s",
            rendered_text="t",
            rendered_html="<p>t</p>",
            status=OutboxEmail.Status.SENT,
            attempt_count=1,
        )

        response = self.client.get(reverse("accounts:password_reset_status", args=[flow_id]))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["state"], "sent")

        session = self.client.session
        flows = session.get(PASSWORD_RESET_FLOWS_SESSION_KEY, {})
        self.assertNotIn(flow_id, flows)
        self.assertIsNone(session.get(PASSWORD_RESET_LAST_FLOW_KEY))


class PasswordResetDoneViewTests(TestCase):
    def test_view_context_exposes_flow_data(self) -> None:
        flow_id = uuid4().hex
        session = self.client.session
        session[PASSWORD_RESET_FLOWS_SESSION_KEY] = {
            flow_id: {"flow_id": flow_id, "state": "queued", "created_at": timezone.now().isoformat()}
        }
        session[PASSWORD_RESET_LAST_FLOW_KEY] = flow_id
        session.save()

        response = self.client.get(reverse("accounts:password_reset_done"))
        self.assertEqual(response.status_code, 200)
        ctx = response.context
        self.assertIn("reset_flow", ctx)
        self.assertEqual(ctx["reset_flow"].get("flow_id"), flow_id)
        self.assertIn("status_url", ctx)
        self.assertIn(flow_id, ctx["status_url"])
