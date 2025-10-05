from __future__ import annotations

from django.db import IntegrityError
from django.test import TestCase

from apps.adsbridge.models import ConversionRecord


class ConversionRecordModelTests(TestCase):
    def _create_record(self, **overrides) -> ConversionRecord:
        defaults = dict(
            kind=ConversionRecord.Kind.LEAD,
            action_key="lead_submit",
            idempotency_key="idem-1",
        )
        defaults.update(overrides)
        return ConversionRecord.objects.create(**defaults)

    def test_idempotency_key_unique(self) -> None:
        self._create_record()
        with self.assertRaises(IntegrityError):
            self._create_record()

    def test_mark_sent_updates_status_and_payload(self) -> None:
        record = self._create_record(idempotency_key="idem-2")
        record.mark_sent({"status": "OK"}, mode="mock")
        record.refresh_from_db()
        self.assertEqual(record.status, ConversionRecord.Status.SENT)
        self.assertEqual(record.google_upload_status, {"status": "OK"})
        self.assertEqual(record.effective_mode, "mock")
        self.assertEqual(record.hold_reason, "")

    def test_mark_held_sets_reason(self) -> None:
        record = self._create_record(idempotency_key="idem-held")
        record.mark_held("Capture mode", mode="capture")
        record.refresh_from_db()
        self.assertEqual(record.status, ConversionRecord.Status.HELD)
        self.assertEqual(record.hold_reason, "Capture mode")
        self.assertEqual(record.effective_mode, "capture")

    def test_queryset_helpers(self) -> None:
        pending = self._create_record(idempotency_key="idem-3")
        sent = self._create_record(idempotency_key="idem-4")
        sent.status = ConversionRecord.Status.SENT
        sent.save(update_fields=["status", "updated_at"])
        held = self._create_record(idempotency_key="idem-5")
        held.status = ConversionRecord.Status.HELD
        held.save(update_fields=["status", "updated_at"])

        self.assertIn(pending, ConversionRecord.objects.pending())
        self.assertIn(sent, ConversionRecord.objects.sent())
        self.assertNotIn(pending, ConversionRecord.objects.sent())
        self.assertIn(held, ConversionRecord.objects.held())
