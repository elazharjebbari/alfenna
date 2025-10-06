from __future__ import annotations

from django.test import TestCase

from apps.messaging.exceptions import TemplateNotFoundError
from apps.messaging.models import EmailTemplate, OutboxEmail
from apps.messaging.services import EmailService, TemplateService


class TemplateServiceTests(TestCase):
    def setUp(self) -> None:
        self.template = EmailTemplate.objects.create(
            slug="tests/template-activation",
            locale="fr",
            version=1,
            subject="Activate {{ user }}",
            html_template="<p>Hello {{ user }}</p>",
            text_template="Hello {{ user }}",
        )

    def test_resolve_returns_template(self) -> None:
        resolved = TemplateService.resolve("tests/template-activation", "fr")
        self.assertEqual(resolved.id, self.template.id)

    def test_resolve_missing_raises(self) -> None:
        with self.assertRaises(TemplateNotFoundError):
            TemplateService.resolve("tests/missing", "fr")

    def test_render_outputs_all_variants(self) -> None:
        composition = TemplateService.render(self.template, {"user": "Marie"})
        self.assertEqual(composition.subject, "Activate Marie")
        self.assertIn("Hello Marie", composition.html_body)
        self.assertEqual(composition.context["user"], "Marie")


class EmailServiceTests(TestCase):
    def setUp(self) -> None:
        self.template = EmailTemplate.objects.create(
            slug="tests/service-reset",
            locale="fr",
            version=3,
            subject="Reset",
            html_template="<p>Reset {{ code }}</p>",
            text_template="Reset {{ code }}",
        )

    def test_enqueue_creates_outbox_entry(self) -> None:
        outbox = EmailService.compose_and_enqueue(
            namespace="accounts",
            purpose="reset",
            template_slug="tests/service-reset",
            to=["user@example.com"],
            context={"code": "123456"},
        )
        self.assertEqual(outbox.namespace, "accounts")
        self.assertEqual(outbox.rendered_text, "Reset 123456")
        self.assertEqual(outbox.rendered_subject, "Reset")
        self.assertEqual(outbox.status, OutboxEmail.Status.QUEUED)

    def test_idempotent_by_dedup_key(self) -> None:
        first = EmailService.compose_and_enqueue(
            namespace="accounts",
            purpose="reset",
            template_slug="tests/service-reset",
            to=["user@example.com"],
            context={"code": "123456"},
        )
        second = EmailService.compose_and_enqueue(
            namespace="accounts",
            purpose="reset",
            template_slug="tests/service-reset",
            to=["user@example.com"],
            context={"code": "123456"},
        )
        self.assertEqual(first.id, second.id)
        self.assertEqual(OutboxEmail.objects.count(), 1)

    def test_subject_override(self) -> None:
        outbox = EmailService.compose_and_enqueue(
            namespace="accounts",
            purpose="reset",
            template_slug="tests/service-reset",
            to=["user@example.com"],
            context={"code": "123456"},
            subject_override="Important",
        )
        self.assertEqual(outbox.rendered_subject, "Important")
        self.assertEqual(outbox.subject_override, "Important")
