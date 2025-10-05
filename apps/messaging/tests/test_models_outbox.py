from __future__ import annotations

from datetime import timedelta

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from apps.messaging.models import EmailTemplate, OutboxEmail


class OutboxModelTests(TestCase):
    def setUp(self) -> None:
        EmailTemplate.objects.create(
            slug="tests/outbox",
            locale="fr",
            version=1,
            subject="Activation",
            html_template="<p>Bonjour</p>",
            text_template="Bonjour",
        )

    def test_deduplication_is_enforced(self) -> None:
        OutboxEmail.objects.create(
            namespace="accounts",
            purpose="activation",
            dedup_key="order-1",
            to=["user@example.com"],
            template_slug="tests/outbox",
        )
        with self.assertRaises(IntegrityError):
            OutboxEmail.objects.create(
                namespace="accounts",
                purpose="activation",
                dedup_key="order-1",
                to=["user@example.com"],
                template_slug="tests/outbox",
            )

    def test_due_ordering_prioritises_priority_then_schedule(self) -> None:
        now = timezone.now()
        e1 = OutboxEmail.objects.create(
            namespace="accounts",
            purpose="activation",
            dedup_key="job-1",
            to=["a@example.com"],
            template_slug="tests/outbox",
            priority=10,
            scheduled_at=now + timedelta(minutes=5),
        )
        e2 = OutboxEmail.objects.create(
            namespace="accounts",
            purpose="activation",
            dedup_key="job-2",
            to=["b@example.com"],
            template_slug="tests/outbox",
            priority=5,
            scheduled_at=now + timedelta(minutes=1),
        )
        e3 = OutboxEmail.objects.create(
            namespace="accounts",
            purpose="activation",
            dedup_key="job-3",
            to=["c@example.com"],
            template_slug="tests/outbox",
            priority=5,
            scheduled_at=now + timedelta(minutes=3),
        )

        due_ids = list(
            OutboxEmail.objects.due_ordered(as_of=now + timedelta(minutes=10)).values_list("id", flat=True)
        )
        self.assertEqual(due_ids, [e2.id, e3.id, e1.id])

    def test_indexes_present(self) -> None:
        index_names = {index.name for index in OutboxEmail._meta.indexes}
        self.assertIn("outbox_status_schedule_idx", index_names)
        self.assertIn("outbox_namespace_status_idx", index_names)


class EmailTemplateQueryTests(TestCase):
    def test_latest_active_version_by_locale(self) -> None:
        EmailTemplate.objects.create(
            slug="tests/query",
            locale="fr",
            version=1,
            subject="Activation FR v1",
            html_template="<p>v1</p>",
            text_template="v1",
        )
        EmailTemplate.objects.create(
            slug="tests/query",
            locale="fr",
            version=2,
            subject="Activation FR v2",
            html_template="<p>v2</p>",
            text_template="v2",
        )
        fallback = EmailTemplate.objects.create(
            slug="tests/query",
            locale="en",
            version=1,
            subject="Activation EN",
            html_template="<p>en</p>",
            text_template="en",
        )
        EmailTemplate.objects.create(
            slug="tests/query",
            locale="fr",
            version=3,
            subject="Activation FR v3 inactive",
            html_template="<p>v3</p>",
            text_template="v3",
            is_active=False,
        )

        fr_template = EmailTemplate.objects.latest_for("tests/query", "fr")
        self.assertIsNotNone(fr_template)
        self.assertEqual(fr_template.version, 2)

        es_template = EmailTemplate.objects.latest_for("tests/query", "es")
        self.assertEqual(es_template.id, fallback.id)
