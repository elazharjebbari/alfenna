from __future__ import annotations

from decimal import Decimal
import os
from pathlib import Path
from unittest.mock import patch
import uuid

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.adsbridge.adapters.google_ads import UploadResult, ResolvedConfig
from apps.adsbridge.models import ConversionRecord
from apps.adsbridge import services, tasks
from apps.billing.models import Order, OrderStatus
from apps.billing.services import EntitlementService
from apps.billing.webhooks import _process_event
from apps.leads.constants import LeadStatus
from apps.leads.models import Lead
from apps.leads.tasks import process_lead


@override_settings(GADS_ENABLED=True, CELERY_TASK_ALWAYS_EAGER=True)
class AdsbridgeIntegrationTests(TestCase):
    def setUp(self) -> None:
        mode_patch = override_settings(ADS_S2S_MODE="on")
        mode_patch.enable()
        self.addCleanup(mode_patch.disable)
        services.load_ads_config.cache_clear()
        tasks._get_adapter.cache_clear()
        self.env_patch = patch.dict(
            os.environ,
            {"GADS_CUSTOMER_ID": "1234567890", "GADS_LOGIN_CUSTOMER_ID": "0987654321"},
            clear=False,
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.on_commit_patch = patch(
            "apps.adsbridge.hooks.transaction.on_commit", lambda fn: fn()
        )
        self.on_commit_patch.start()
        self.addCleanup(self.on_commit_patch.stop)
        cache.clear()

        resolved = ResolvedConfig(
            developer_token="token",
            client_id="client",
            client_secret="secret",
            refresh_token="refresh",
            login_customer_id="0987654321",
            customer_id="1234567890",
            linked_customer_id=None,
            path=Path("cred.yaml"),
            path_exists=True,
            path_source="test",
            path_env_var=None,
            sources={
                "developer_token": "env:GADS_DEVELOPER_TOKEN",
                "client_id": "env:GADS_CLIENT_ID",
                "client_secret": "env:GADS_CLIENT_SECRET",
                "refresh_token": "env:GADS_REFRESH_TOKEN",
                "login_customer_id": "env:GADS_LOGIN_CUSTOMER_ID",
                "customer_id": "env:GADS_CUSTOMER_ID",
                "linked_customer_id": "missing",
            },
        )
        patcher = patch(
            "apps.adsbridge.adapters.google_ads.GoogleAdsAdapter.load_configuration",
            return_value=resolved,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _make_lead(self, **overrides) -> Lead:
        defaults = dict(
            form_kind="contact_full",
            campaign="",
            source="web",
            utm_source="",
            utm_medium="",
            utm_campaign="",
            context={"ads_attribution": {"gclid": "G123", "gclsrc": "aw"}},
            email="demo@example.com",
            first_name="Demo",
            last_name="User",
            phone="0612345678",
            currency="EUR",
            consent=True,
            idempotency_key=str(uuid.uuid4()),
            status=LeadStatus.PENDING,
        )
        defaults.update(overrides)
        return Lead.objects.create(**defaults)

    def _make_order(self, **overrides) -> Order:
        defaults = dict(
            email="buyer@example.com",
            amount_subtotal=15000,
            tax_amount=0,
            amount_total=15000,
            currency="EUR",
            status=OrderStatus.PENDING,
            idempotency_key=str(uuid.uuid4()),
        )
        defaults.update(overrides)
        return Order.objects.create(**defaults)

    @patch("apps.adsbridge.tasks._get_adapter")
    def test_lead_pipeline_reaches_sent_status(self, mock_adapter) -> None:
        adapter = mock_adapter.return_value
        adapter.upload_click_conversion.return_value = UploadResult(status="OK", payload={"resource_name": "dummy"})
        adapter.customer_id = "0987654321"
        adapter.customer_id = "0987654321"

        lead = self._make_lead()

        process_lead.apply(args=[lead.id])

        record = ConversionRecord.objects.get(kind=ConversionRecord.Kind.LEAD)
        self.assertEqual(record.status, ConversionRecord.Status.SENT)
        self.assertEqual(record.google_upload_status.get("resource_name"), "dummy")
        adapter.upload_click_conversion.assert_called_once()

    @patch("apps.adsbridge.tasks._get_adapter")
    def test_purchase_pipeline_reaches_sent_status(self, mock_adapter) -> None:
        adapter = mock_adapter.return_value
        adapter.upload_click_conversion.return_value = UploadResult(status="OK", payload={"resource_name": "purchase"})
        adapter.customer_id = "0987654321"

        order = self._make_order()
        self._make_lead(order=order, status=LeadStatus.VALID, consent=True)

        EntitlementService.grant_entitlement(order, "payment_intent.succeeded", {"data": {"object": {}}})

        record = ConversionRecord.objects.filter(kind=ConversionRecord.Kind.PURCHASE).latest("id")
        self.assertEqual(record.status, ConversionRecord.Status.SENT)
        self.assertEqual(record.order_id, str(order.id))
        self.assertEqual(record.value, Decimal("150.00"))
        adapter.upload_click_conversion.assert_called()

    @patch("apps.adsbridge.tasks._get_adapter")
    def test_refund_pipeline_creates_adjustment(self, mock_adapter) -> None:
        adapter = mock_adapter.return_value
        adapter.upload_click_conversion.return_value = UploadResult(status="OK", payload={"resource_name": "purchase"})
        adapter.upload_adjustment.return_value = UploadResult(status="OK", payload={"resource_name": "adjust"})
        adapter.customer_id = "0987654321"

        order = self._make_order()
        self._make_lead(order=order, status=LeadStatus.VALID, consent=True)
        EntitlementService.grant_entitlement(order, "payment_intent.succeeded", {"data": {"object": {}}})

        event = {"type": "charge.refunded", "data": {"object": {"metadata": {"order_id": str(order.id)}}}}
        _process_event(event)

        record = ConversionRecord.objects.filter(kind=ConversionRecord.Kind.ADJUSTMENT).latest("id")
        self.assertEqual(record.status, ConversionRecord.Status.SENT)
        self.assertEqual(record.adjustment_type, "RETRACTION")
        adapter.upload_adjustment.assert_called()

    @patch("apps.adsbridge.tasks._get_adapter")
    def test_consent_off_lead_results_in_skipped_record(self, mock_adapter) -> None:
        adapter = mock_adapter.return_value
        adapter.upload_click_conversion.return_value = UploadResult(status="OK", payload={"resource_name": "dummy"})
        adapter.customer_id = "0987654321"

        lead = self._make_lead(consent=False)

        process_lead.apply(args=[lead.id])

        record = ConversionRecord.objects.get(kind=ConversionRecord.Kind.LEAD)
        self.assertEqual(record.status, ConversionRecord.Status.SKIPPED_NO_CONSENT)
        self.assertEqual(record.effective_mode, "on")
        adapter.upload_click_conversion.assert_not_called()
