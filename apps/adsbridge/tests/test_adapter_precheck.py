from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from apps.adsbridge.adapters.google_ads import (
    GoogleAdsActionNotFoundError,
    GoogleAdsAdapter,
    ResolvedConfig,
)


class GoogleAdsAdapterPreverifyTests(SimpleTestCase):
    def setUp(self) -> None:
        self.resolved = _resolved_config()
        loader = patch(
            "apps.adsbridge.adapters.google_ads.GoogleAdsAdapter.load_configuration",
            return_value=self.resolved,
        )
        loader.start()
        self.addCleanup(loader.stop)

        self.conversion_service = MagicMock()
        self.google_service = MagicMock()

        def _get_service(name: str):
            if name == "ConversionUploadService":
                return self.conversion_service
            if name == "ConversionAdjustmentUploadService":
                return MagicMock()
            if name == "GoogleAdsService":
                return self.google_service
            raise AssertionError(f"Unexpected service requested: {name}")

        self.client = MagicMock()
        self.client.get_service.side_effect = _get_service
        self.client.get_type.side_effect = lambda _: MagicMock()

    @override_settings(
        GADS_CUSTOMER_ID="0987654321",
        GADS_CONVERSION_ACTIONS={"lead_submit": {"id": "1111111111"}},
        GADS_PREVERIFY_ACTIONS=True,
    )
    def test_missing_conversion_action_raises_before_upload(self) -> None:
        self.google_service.search.return_value = []

        adapter = GoogleAdsAdapter(client=self.client)

        with self.assertRaises(GoogleAdsActionNotFoundError) as ctx:
            adapter.upload_click_conversion(
                customer_id="0987654321",
                action_id="lead_submit",
                click_id_field="gclid",
                click_id="test",
                value=None,
                currency=None,
                order_id="order-1",
                event_at=self._event_time(),
            )

        message = str(ctx.exception)
        self.assertIn("ACTION_NOT_FOUND", message)
        self.assertFalse(self.conversion_service.upload_click_conversions.called)

    @override_settings(
        GADS_CUSTOMER_ID="0987654321",
        GADS_CONVERSION_ACTIONS={"lead_submit": {"id": "1111111111"}},
        GADS_PREVERIFY_ACTIONS=True,
    )
    def test_disabled_conversion_action_raises(self) -> None:
        self.google_service.search.return_value = [
            SimpleNamespace(
                conversion_action=SimpleNamespace(status=SimpleNamespace(name="REMOVED"))
            )
        ]

        adapter = GoogleAdsAdapter(client=self.client)

        with self.assertRaises(GoogleAdsActionNotFoundError) as ctx:
            adapter.upload_click_conversion(
                customer_id="0987654321",
                action_id="lead_submit",
                click_id_field="gclid",
                click_id="test",
                value=None,
                currency=None,
                order_id="order-2",
                event_at=self._event_time(),
            )

        self.assertIn("status=REMOVED", str(ctx.exception))
        self.assertFalse(self.conversion_service.upload_click_conversions.called)

    @override_settings(
        GADS_CUSTOMER_ID="0987654321",
        GADS_CONVERSION_ACTIONS={"lead_submit": {"id": "1111111111"}},
        GADS_PREVERIFY_ACTIONS=True,
    )
    def test_valid_conversion_action_calls_upload(self) -> None:
        self.google_service.search.return_value = [
            SimpleNamespace(
                conversion_action=SimpleNamespace(status=SimpleNamespace(name="ENABLED"))
            )
        ]
        self.conversion_service.upload_click_conversions.return_value = SimpleNamespace(results=[])

        adapter = GoogleAdsAdapter(client=self.client)
        result = adapter.upload_click_conversion(
            customer_id="0987654321",
            action_id="lead_submit",
            click_id_field="gclid",
            click_id="test",
            value=None,
            currency=None,
            order_id="order-3",
            event_at=self._event_time(),
        )

        self.assertEqual(result.status, "OK")
        self.conversion_service.upload_click_conversions.assert_called_once()
        self.assertEqual(self.google_service.search.call_count, 1)

    def _event_time(self):
        from datetime import datetime

        return datetime.utcnow()


def _resolved_config() -> ResolvedConfig:
    sources = {
        "developer_token": "env:GADS_DEVELOPER_TOKEN",
        "client_id": "env:GADS_CLIENT_ID",
        "client_secret": "env:GADS_CLIENT_SECRET",
        "refresh_token": "env:GADS_REFRESH_TOKEN",
        "login_customer_id": "env:GADS_LOGIN_CUSTOMER_ID",
        "customer_id": "env:GADS_CUSTOMER_ID",
        "linked_customer_id": "missing",
    }
    return ResolvedConfig(
        developer_token="token",
        client_id="client",
        client_secret="secret",
        refresh_token="refresh",
        login_customer_id="1234567890",
        customer_id="0987654321",
        linked_customer_id=None,
        path=Path("cred.yaml"),
        path_exists=True,
        path_source="env",
        path_env_var="GADS_CONFIGURATION_PATH",
        sources=sources,
    )
