from __future__ import annotations

from decimal import Decimal
import os
from unittest.mock import patch
import uuid

from django.db import transaction
from django.test import TestCase, override_settings

from apps.adsbridge import hooks, services
from apps.adsbridge.models import ConversionRecord
from apps.billing.models import Order
from apps.leads.constants import LeadStatus
from apps.leads.models import Lead


class HooksTests(TestCase):
    def setUp(self) -> None:
        mode_patch = override_settings(ADS_S2S_MODE="on")
        mode_patch.enable()
        self.addCleanup(mode_patch.disable)
        self.env_patch = patch.dict(
            os.environ,
            {"GADS_CUSTOMER_ID": "1234567890", "GADS_LOGIN_CUSTOMER_ID": "0987654321"},
            clear=False,
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.on_commit_patch = patch(
            "apps.adsbridge.hooks.transaction.on_commit", lambda fn: fn())
        self.on_commit_patch.start()
        self.addCleanup(self.on_commit_patch.stop)
        services.load_ads_config.cache_clear()

    def _lead(self, **overrides) -> Lead:
        defaults = dict(
            form_kind="contact_full",
            campaign="",
            source="web",
            utm_source="",
            utm_medium="",
            utm_campaign="",
            context={"ads_attribution": {"gclid": "G123", "gclsrc": "aw"}},
            email="test@example.com",
            first_name="Test",
            last_name="User",
            phone="0612345678",
            currency="EUR",
            consent=True,
            idempotency_key=str(uuid.uuid4()),
            status=LeadStatus.VALID,
        )
        defaults.update(overrides)
        return Lead.objects.create(**defaults)

    def _order(self, **overrides) -> Order:
        defaults = dict(
            email="buyer@example.com",
            amount_subtotal=10000,
            tax_amount=0,
            amount_total=10000,
            currency="EUR",
            idempotency_key=str(uuid.uuid4()),
        )
        defaults.update(overrides)
        return Order.objects.create(**defaults)

    @patch("apps.adsbridge.hooks.enqueue_conversion")
    def test_record_lead_conversion_with_consent_enqueues(self, mock_enqueue) -> None:
        lead = self._lead()

        record = hooks.record_lead_conversion(lead)

        self.assertIsNotNone(record)
        self.assertEqual(record.status, ConversionRecord.Status.PENDING)
        self.assertEqual(record.gclid, "G123")
        self.assertEqual(record.action_key, "lead_submit")
        self.assertTrue(record.enhanced_identifiers)
        self.assertEqual(record.effective_mode, "on")
        mock_enqueue.assert_called_once_with(record.id)

    @patch("apps.adsbridge.hooks.enqueue_conversion")
    def test_record_lead_conversion_without_consent_skips(self, mock_enqueue) -> None:
        lead = self._lead(consent=False, context={"ads_attribution": {"gclid": "G123"}})

        record = hooks.record_lead_conversion(lead)

        self.assertIsNotNone(record)
        self.assertEqual(record.status, ConversionRecord.Status.SKIPPED_NO_CONSENT)
        self.assertEqual(record.last_error, "NO_CONSENT")
        self.assertEqual(record.effective_mode, "on")
        mock_enqueue.assert_not_called()

    @patch("apps.adsbridge.hooks.enqueue_conversion")
    def test_record_order_purchase_uses_lead_and_amount(self, mock_enqueue) -> None:
        order = self._order()
        lead = self._lead(order=order, status=LeadStatus.VALID)

        record = hooks.record_order_purchase(order, payload={})

        self.assertIsNotNone(record)
        self.assertEqual(record.kind, ConversionRecord.Kind.PURCHASE)
        self.assertEqual(record.order_id, str(order.id))
        self.assertEqual(record.value, Decimal("100.00"))
        self.assertEqual(record.lead_id, str(lead.id))
        self.assertEqual(record.effective_mode, "on")
        mock_enqueue.assert_called_once_with(record.id)

    @patch("apps.adsbridge.hooks.enqueue_conversion")
    def test_record_order_refund_creates_adjustment(self, mock_enqueue) -> None:
        order = self._order()
        self._lead(order=order, status=LeadStatus.VALID)

        record = hooks.record_order_refund(order, payload={})

        self.assertIsNotNone(record)
        self.assertEqual(record.kind, ConversionRecord.Kind.ADJUSTMENT)
        self.assertEqual(record.adjustment_type, "RETRACTION")
        self.assertEqual(record.status, ConversionRecord.Status.PENDING)
        self.assertEqual(record.effective_mode, "on")
        mock_enqueue.assert_called_once_with(record.id)

    @patch("apps.adsbridge.hooks.enqueue_conversion")
    def test_capture_mode_holds_records(self, mock_enqueue) -> None:
        with override_settings(ADS_S2S_MODE="capture"):
            services.load_ads_config.cache_clear()
            lead = self._lead()
            record = hooks.record_lead_conversion(lead)

        self.assertIsNotNone(record)
        self.assertEqual(record.status, ConversionRecord.Status.HELD)
        self.assertEqual(record.hold_reason, "Capture mode active")
        self.assertEqual(record.effective_mode, "capture")
        mock_enqueue.assert_not_called()

    @patch("apps.adsbridge.hooks.enqueue_conversion")
    def test_off_mode_returns_none(self, mock_enqueue) -> None:
        with override_settings(ADS_S2S_MODE="off"):
            services.load_ads_config.cache_clear()
            lead = self._lead()
            record = hooks.record_lead_conversion(lead)

        self.assertIsNone(record)
        mock_enqueue.assert_not_called()
