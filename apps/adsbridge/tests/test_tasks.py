from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.adsbridge import services
from apps.adsbridge.adapters.google_ads import (
    GoogleAdsActionNotFoundError,
    GoogleAdsDuplicateError,
    GoogleAdsPartialFailureError,
    UploadResult,
)
from apps.adsbridge.models import ConversionRecord
from apps.adsbridge import tasks


def _stub_config() -> services.AdsConfig:
    return services.AdsConfig(
        customer_id="123-456-7890",
        login_customer_id="123-456-7890",
        default_currency="EUR",
        conversion_actions={
            "lead_submit": services.ConversionAction(key="lead_submit", action_id="111", type="CLICK"),
            "purchase": services.ConversionAction(key="purchase", action_id="222", type="CLICK"),
            "purchase_adjustment": services.ConversionAction(key="purchase_adjustment", action_id="333", type="ADJUSTMENT"),
        },
    )


class ConversionTasksTests(TestCase):
    def setUp(self) -> None:
        mode_patch = override_settings(ADS_S2S_MODE="on")
        mode_patch.enable()
        self.addCleanup(mode_patch.disable)
        services.load_ads_config.cache_clear()
        tasks._get_adapter.cache_clear()

    @override_settings(GADS_ENABLED=True)
    @patch("apps.adsbridge.tasks._get_adapter")
    @patch("apps.adsbridge.tasks.services.load_ads_config", side_effect=lambda: _stub_config())
    def test_upload_click_conversion_marks_sent(self, mock_config, mock_adapter) -> None:
        adapter = MagicMock()
        adapter.upload_click_conversion.return_value = UploadResult(status="OK", payload={"resource_name": "result/1"})
        adapter.customer_id = "1234567890"
        mock_adapter.return_value = adapter

        record = ConversionRecord.objects.create(
            kind=ConversionRecord.Kind.LEAD,
            action_key="lead_submit",
            idempotency_key="idem-100",
            gclid="G123",
        )

        tasks.upload_click_conversion.apply(args=[record.id])

        record.refresh_from_db()
        self.assertEqual(record.status, ConversionRecord.Status.SENT)
        self.assertEqual(record.attempt_count, 1)
        self.assertEqual(record.google_upload_status.get("resource_name"), "result/1")
        self.assertEqual(record.effective_mode, "on")
        adapter.upload_click_conversion.assert_called_once()

    @override_settings(GADS_ENABLED=True)
    @patch("apps.adsbridge.tasks._get_adapter")
    @patch("apps.adsbridge.tasks.services.load_ads_config", side_effect=lambda: _stub_config())
    def test_upload_click_conversion_duplicate_treated_as_sent(self, mock_config, mock_adapter) -> None:
        adapter = MagicMock()
        adapter.upload_click_conversion.side_effect = GoogleAdsDuplicateError("duplicate")
        adapter.customer_id = "1234567890"
        mock_adapter.return_value = adapter

        record = ConversionRecord.objects.create(
            kind=ConversionRecord.Kind.LEAD,
            action_key="lead_submit",
            idempotency_key="idem-101",
            gclid="G123",
        )

        tasks.upload_click_conversion.apply(args=[record.id])

        record.refresh_from_db()
        self.assertEqual(record.status, ConversionRecord.Status.SENT)
        self.assertIn("DUPLICATE", record.google_upload_status.get("status"))
        self.assertEqual(record.effective_mode, "on")

    @override_settings(GADS_ENABLED=True)
    @patch("apps.adsbridge.tasks._get_adapter")
    @patch("apps.adsbridge.tasks.services.load_ads_config", side_effect=lambda: _stub_config())
    def test_upload_click_conversion_action_not_found_marks_error(self, mock_config, mock_adapter) -> None:
        adapter = MagicMock()
        adapter.customer_id = "1234567890"
        adapter.upload_click_conversion.side_effect = GoogleAdsActionNotFoundError(
            "customers/1234567890/conversionActions/111",
            alias="legacy-id",
            status="NOT_FOUND",
            customer_id="1234567890",
        )
        mock_adapter.return_value = adapter

        record = ConversionRecord.objects.create(
            kind=ConversionRecord.Kind.LEAD,
            action_key="lead_submit",
            idempotency_key="idem-105",
            gclid="G123",
        )

        tasks.upload_click_conversion.apply(args=[record.id])

        record.refresh_from_db()
        self.assertEqual(record.status, ConversionRecord.Status.ERROR)
        self.assertEqual(record.attempt_count, 1)
        payload = record.google_upload_status
        self.assertEqual(payload.get("error_code"), "ACTION_NOT_FOUND")
        detail = payload.get("error_detail", {})
        self.assertEqual(detail.get("alias"), "lead_submit")
        self.assertEqual(detail.get("identifier"), "legacy-id")
        self.assertEqual(detail.get("customer_id"), "1234567890")
        self.assertIn("ACTION_NOT_FOUND", record.last_error or "")
        adapter.upload_click_conversion.assert_called_once()

    @override_settings(GADS_ENABLED=True)
    @patch("apps.adsbridge.tasks._get_adapter")
    @patch("apps.adsbridge.tasks.services.load_ads_config", side_effect=lambda: _stub_config())
    def test_upload_adjustment_requires_order_id(self, mock_config, mock_adapter) -> None:
        adapter = MagicMock()
        adapter.customer_id = "1234567890"
        mock_adapter.return_value = adapter

        record = ConversionRecord.objects.create(
            kind=ConversionRecord.Kind.ADJUSTMENT,
            action_key="purchase_adjustment",
            idempotency_key="idem-102",
        )

        tasks.upload_adjustment.apply(args=[record.id])

        record.refresh_from_db()
        self.assertEqual(record.status, ConversionRecord.Status.ERROR)
        self.assertEqual(record.effective_mode, "on")
        adapter.upload_adjustment.assert_not_called()

    @override_settings(GADS_ENABLED=True)
    @patch("apps.adsbridge.tasks._get_adapter")
    @patch("apps.adsbridge.tasks.services.load_ads_config", side_effect=lambda: _stub_config())
    def test_upload_adjustment_success(self, mock_config, mock_adapter) -> None:
        adapter = MagicMock()
        adapter.upload_adjustment.return_value = UploadResult(status="OK", payload={"resource_name": "adjust/1"})
        adapter.customer_id = "1234567890"
        mock_adapter.return_value = adapter

        record = ConversionRecord.objects.create(
            kind=ConversionRecord.Kind.ADJUSTMENT,
            action_key="purchase_adjustment",
            idempotency_key="idem-103",
            order_id="ORDER123",
            adjustment_type="RETRACTION",
        )

        tasks.upload_adjustment.apply(args=[record.id])

        record.refresh_from_db()
        self.assertEqual(record.status, ConversionRecord.Status.SENT)
        self.assertEqual(record.google_upload_status.get("resource_name"), "adjust/1")
        self.assertEqual(record.effective_mode, "on")
        adapter.upload_adjustment.assert_called_once()

    @override_settings(GADS_ENABLED=True)
    @patch("apps.adsbridge.tasks._get_adapter")
    @patch("apps.adsbridge.tasks.services.load_ads_config", side_effect=lambda: _stub_config())
    def test_upload_click_conversion_partial_failure_persists_details(self, mock_config, mock_adapter) -> None:
        adapter = MagicMock()
        adapter.customer_id = "1234567890"
        partial_error = GoogleAdsPartialFailureError(
            "partial failure: codes=INVALID_CLICK_ID,MISSING_CLICK_IDENTIFIER; first=MISSING_CLICK_IDENTIFIER at operations[0] > create: Missing click id",
            codes="INVALID_CLICK_ID,MISSING_CLICK_IDENTIFIER",
            errors=[
                {
                    "code": "MISSING_CLICK_IDENTIFIER",
                    "location": "operations[0] > create",
                    "message": "Missing click id",
                },
                {
                    "code": "INVALID_CLICK_ID",
                    "location": "operations[1] > create",
                    "message": "Invalid click id",
                },
            ],
            status_message="partial failure",
        )
        adapter.upload_click_conversion.side_effect = partial_error
        mock_adapter.return_value = adapter

        record = ConversionRecord.objects.create(
            kind=ConversionRecord.Kind.LEAD,
            action_key="lead_submit",
            idempotency_key="idem-109",
            gclid="G123",
        )

        tasks.upload_click_conversion.apply(args=[record.id])

        record.refresh_from_db()
        self.assertEqual(record.status, ConversionRecord.Status.ERROR)
        payload = record.google_upload_status
        self.assertEqual(
            payload.get("error_code"),
            "INVALID_CLICK_ID,MISSING_CLICK_IDENTIFIER",
        )
        self.assertEqual(payload.get("status_message"), "partial failure")
        self.assertEqual(len(payload.get("errors", [])), 2)
        self.assertEqual(
            payload["errors"][0]["location"],
            "operations[0] > create",
        )
        self.assertIn("partial failure", record.last_error or "")

    @override_settings(GADS_ENABLED=True)
    @patch("apps.adsbridge.tasks._get_adapter")
    @patch("apps.adsbridge.tasks.services.load_ads_config", side_effect=lambda: _stub_config())
    def test_upload_adjustment_action_not_found_marks_error(self, mock_config, mock_adapter) -> None:
        adapter = MagicMock()
        adapter.customer_id = "1234567890"
        adapter.upload_adjustment.side_effect = GoogleAdsActionNotFoundError(
            "customers/1234567890/conversionActions/333",
            status="REMOVED",
            customer_id="1234567890",
        )
        mock_adapter.return_value = adapter

        record = ConversionRecord.objects.create(
            kind=ConversionRecord.Kind.ADJUSTMENT,
            action_key="purchase_adjustment",
            idempotency_key="idem-106",
            order_id="ORDER123",
            adjustment_type="RETRACTION",
        )

        tasks.upload_adjustment.apply(args=[record.id])

        record.refresh_from_db()
        self.assertEqual(record.status, ConversionRecord.Status.ERROR)
        payload = record.google_upload_status
        self.assertEqual(payload.get("error_code"), "ACTION_NOT_FOUND")
        detail = payload.get("error_detail", {})
        self.assertEqual(detail.get("alias"), "purchase_adjustment")
        self.assertNotIn("identifier", detail)  # alias matches identifier
        self.assertEqual(detail.get("status"), "REMOVED")
        adapter.upload_adjustment.assert_called_once()

    @override_settings(GADS_ENABLED=True)
    @patch("apps.adsbridge.tasks._get_adapter")
    @patch("apps.adsbridge.tasks.services.load_ads_config", side_effect=lambda: _stub_config())
    def test_enqueue_conversion_dispatches_by_kind(self, mock_config, mock_adapter) -> None:
        adapter = MagicMock()
        mock_adapter.return_value = adapter

        lead = ConversionRecord.objects.create(
            kind=ConversionRecord.Kind.LEAD,
            action_key="lead_submit",
            idempotency_key="idem-200",
            gclid="G123",
        )
        adj = ConversionRecord.objects.create(
            kind=ConversionRecord.Kind.ADJUSTMENT,
            action_key="purchase_adjustment",
            idempotency_key="idem-201",
            order_id="ORD-1",
            adjustment_type="RETRACTION",
        )

        with patch.object(tasks.upload_click_conversion, "delay") as mock_click, patch.object(tasks.upload_adjustment, "delay") as mock_adjust:
            tasks.enqueue_conversion(lead.id)
            tasks.enqueue_conversion(adj.id)

        mock_click.assert_called_once_with(lead.id)
        mock_adjust.assert_called_once_with(adj.id)

    @override_settings(GADS_ENABLED=True, ADS_S2S_MODE="capture")
    @patch("apps.adsbridge.tasks.services.load_ads_config", side_effect=lambda: _stub_config())
    def test_enqueue_conversion_in_capture_mode_marks_held(self, mock_config) -> None:
        record = ConversionRecord.objects.create(
            kind=ConversionRecord.Kind.LEAD,
            action_key="lead_submit",
            idempotency_key="idem-300",
            gclid="G123",
        )

        with patch.object(tasks.upload_click_conversion, "delay") as mock_delay:
            tasks.enqueue_conversion(record.id)

        record.refresh_from_db()
        self.assertEqual(record.status, ConversionRecord.Status.HELD)
        self.assertEqual(record.hold_reason, "Capture mode active")
        self.assertEqual(record.effective_mode, "capture")
        mock_delay.assert_not_called()

    @override_settings(GADS_ENABLED=True, ADS_S2S_MODE="mock")
    @patch("apps.adsbridge.tasks._get_adapter")
    @patch("apps.adsbridge.tasks.services.load_ads_config", side_effect=lambda: _stub_config())
    def test_mock_mode_marks_sent_without_error(self, mock_config, mock_adapter) -> None:
        adapter = MagicMock()
        adapter.upload_click_conversion.return_value = UploadResult(status="MOCK", payload={"resource_name": "mock/1"})
        adapter.customer_id = "1234567890"
        mock_adapter.return_value = adapter

        record = ConversionRecord.objects.create(
            kind=ConversionRecord.Kind.LEAD,
            action_key="lead_submit",
            idempotency_key="idem-400",
            gclid="G123",
        )

        tasks.upload_click_conversion.apply(args=[record.id])

        record.refresh_from_db()
        self.assertEqual(record.status, ConversionRecord.Status.SENT)
        self.assertEqual(record.effective_mode, "mock")
        self.assertEqual(record.google_upload_status.get("resource_name"), "mock/1")
