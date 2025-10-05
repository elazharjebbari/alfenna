from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from apps.adsbridge import conf as ads_conf
from apps.adsbridge.adapters.google_ads import (
    GoogleAdsAdapterError,
    GoogleAdsException,
    ResolvedConfig,
)
from apps.adsbridge.models import ConversionRecord


class AdsDiagCommandTests(TestCase):
    def test_command_returns_zero_when_no_errors(self) -> None:
        exit_code = call_command("ads_diag")
        self.assertIsNone(exit_code)

    def test_command_returns_two_when_errors_present(self) -> None:
        ConversionRecord.objects.create(
            kind=ConversionRecord.Kind.LEAD,
            action_key="lead_submit",
            idempotency_key="idem-errs",
            status=ConversionRecord.Status.ERROR,
            last_error="boom",
        )

        with self.assertRaises(SystemExit) as ctx:
            call_command("ads_diag")
        self.assertEqual(ctx.exception.code, 2)

    def test_command_ping_failure_returns_error(self) -> None:
        resolved = _resolved_config()
        with patch(
            "apps.adsbridge.management.commands.ads_diag.GoogleAdsAdapter.load_configuration",
            return_value=resolved,
        ), patch(
            "apps.adsbridge.management.commands.ads_diag.GoogleAdsAdapter",
            side_effect=GoogleAdsAdapterError("boom"),
        ):
            with self.assertRaises(SystemExit) as ctx:
                call_command("ads_diag", "--ping")
        self.assertEqual(ctx.exception.code, 2)

    def test_show_config_masks_identifiers(self) -> None:
        resolved = _resolved_config()
        with patch(
            "apps.adsbridge.management.commands.ads_diag.GoogleAdsAdapter.load_configuration",
            return_value=resolved,
        ):
            stdout = io.StringIO()
            with patch("sys.stdout", stdout):
                call_command("ads_diag", "--show-config")
        output = stdout.getvalue()
        mode_state = ads_conf.describe_mode()
        self.assertIn(f"Google Ads S2S mode: {mode_state.mode}", output)
        self.assertIn(ads_conf.mode_message(), output)
        if mode_state.upload:
            self.assertNotIn("Uploads to Google Ads are currently disabled.", output)
        else:
            self.assertIn("Uploads to Google Ads are currently disabled.", output)
        self.assertIn("***54321", output)
        self.assertIn("source=env:GADS_CUSTOMER_ID", output)
        self.assertIn("source=env", output)  # path metadata includes source

    def test_verify_customer_success(self) -> None:
        resolved = _resolved_config()
        adapter = MagicMock()
        adapter.customer_id = resolved.customer_id
        adapter.login_customer_id = resolved.login_customer_id
        service = adapter._client.get_service.return_value
        service.search.return_value = [
            SimpleNamespace(
                customer=SimpleNamespace(
                    id=resolved.customer_id,
                    manager=False,
                    descriptive_name="Demo Customer",
                )
            )
        ]

        with patch(
            "apps.adsbridge.management.commands.ads_diag.GoogleAdsAdapter.load_configuration",
            return_value=resolved,
        ), patch(
            "apps.adsbridge.management.commands.ads_diag.GoogleAdsAdapter",
            return_value=adapter,
        ):
            stdout = io.StringIO()
            with patch("sys.stdout", stdout):
                exit_code = call_command("ads_diag", "--verify-customer")

        self.assertIsNone(exit_code)
        self.assertIn("Customer verified: id=", stdout.getvalue())

    def test_verify_customer_failure(self) -> None:
        resolved = _resolved_config()
        adapter = MagicMock()
        adapter.customer_id = resolved.customer_id
        adapter.login_customer_id = resolved.login_customer_id
        service = adapter._client.get_service.return_value
        service.search.side_effect = Exception("fail")

        with patch(
            "apps.adsbridge.management.commands.ads_diag.GoogleAdsAdapter.load_configuration",
            return_value=resolved,
        ), patch(
            "apps.adsbridge.management.commands.ads_diag.GoogleAdsAdapter",
            return_value=adapter,
        ):
            with self.assertRaises(SystemExit) as ctx:
                call_command("ads_diag", "--verify-customer")

        self.assertEqual(ctx.exception.code, 2)

    def test_verify_customer_permission_denied(self) -> None:
        resolved = _resolved_config()
        adapter = MagicMock()
        adapter.customer_id = resolved.customer_id
        adapter.login_customer_id = resolved.login_customer_id
        service = adapter._client.get_service.return_value

        failure = SimpleNamespace(
            errors=[
                SimpleNamespace(
                    error_code=SimpleNamespace(
                        authorization_error=SimpleNamespace(name="USER_PERMISSION_DENIED"),
                        request_error=None,
                    ),
                    message="no access",
                )
            ]
        )
        exc = GoogleAdsException("permission", None, failure, "req-1")
        service.search.side_effect = exc

        with patch(
            "apps.adsbridge.management.commands.ads_diag.GoogleAdsAdapter.load_configuration",
            return_value=resolved,
        ), patch(
            "apps.adsbridge.management.commands.ads_diag.GoogleAdsAdapter",
            return_value=adapter,
        ):
            stderr = io.StringIO()
            with patch("sys.stderr", stderr):
                with self.assertRaises(SystemExit) as ctx:
                    call_command("ads_diag", "--verify-customer")

        self.assertEqual(ctx.exception.code, 2)
        output = stderr.getvalue()
        self.assertIn("USER_PERMISSION_DENIED", output)
        self.assertIn(resolved.customer_id, output)
        self.assertIn(resolved.login_customer_id, output)

    def test_verify_customer_invalid_customer_id(self) -> None:
        resolved = _resolved_config()
        adapter = MagicMock()
        adapter.customer_id = resolved.customer_id
        adapter.login_customer_id = resolved.login_customer_id
        service = adapter._client.get_service.return_value

        failure = SimpleNamespace(
            errors=[
                SimpleNamespace(
                    error_code=SimpleNamespace(
                        authorization_error=None,
                        request_error=SimpleNamespace(name="INVALID_CUSTOMER_ID"),
                    ),
                    message="invalid",
                )
            ]
        )
        exc = GoogleAdsException("invalid", None, failure, "req-2")
        service.search.side_effect = exc

        with patch(
            "apps.adsbridge.management.commands.ads_diag.GoogleAdsAdapter.load_configuration",
            return_value=resolved,
        ), patch(
            "apps.adsbridge.management.commands.ads_diag.GoogleAdsAdapter",
            return_value=adapter,
        ):
            stderr = io.StringIO()
            with patch("sys.stderr", stderr):
                with self.assertRaises(SystemExit) as ctx:
                    call_command("ads_diag", "--verify-customer")

        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("INVALID_CUSTOMER_ID", stderr.getvalue())


class AdsReleaseCommandTests(TestCase):
    def setUp(self) -> None:
        mode_patch = override_settings(ADS_S2S_MODE="on")
        mode_patch.enable()
        self.addCleanup(mode_patch.disable)

    @patch("apps.adsbridge.tasks.enqueue_conversion")
    def test_release_command_requeues_records(self, mock_enqueue) -> None:
        record = ConversionRecord.objects.create(
            kind=ConversionRecord.Kind.LEAD,
            action_key="lead_submit",
            idempotency_key="held-1",
            status=ConversionRecord.Status.HELD,
            hold_reason="Capture mode active",
        )

        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            call_command("ads_release", "--all")

        record.refresh_from_db()
        self.assertEqual(record.status, ConversionRecord.Status.PENDING)
        self.assertEqual(record.hold_reason, "")
        mock_enqueue.assert_called_once_with(record.id)

    def test_release_command_blocks_in_capture_mode(self) -> None:
        record = ConversionRecord.objects.create(
            kind=ConversionRecord.Kind.LEAD,
            action_key="lead_submit",
            idempotency_key="held-2",
            status=ConversionRecord.Status.HELD,
        )

        with override_settings(ADS_S2S_MODE="capture"):
            with self.assertRaises(SystemExit) as ctx:
                call_command("ads_release", "--all")

        self.assertEqual(ctx.exception.code, 2)
        record.refresh_from_db()
        self.assertEqual(record.status, ConversionRecord.Status.HELD)


class AdsVerifyActionsCommandTests(TestCase):
    def setUp(self) -> None:
        self.resolved = _resolved_config()
        loader = patch(
            "apps.adsbridge.management.commands.ads_verify_actions.GoogleAdsAdapter.load_configuration",
            return_value=self.resolved,
        )
        self.load_patch = loader.start()
        self.addCleanup(loader.stop)

        client_mock = MagicMock()
        self.client_instance = MagicMock()
        self.client_instance.get_service.return_value = MagicMock()
        client_mock.load_from_dict.return_value = self.client_instance
        client_patch = patch(
            "apps.adsbridge.management.commands.ads_verify_actions.GoogleAdsClient",
            client_mock,
        )
        client_patch.start()
        self.addCleanup(client_patch.stop)
        self.google_client = client_mock
        self.service = self.client_instance.get_service.return_value

    @override_settings(
        GADS_CUSTOMER_ID="0987654321",
        GADS_CONVERSION_ACTIONS={"lead_submit": {"id": "1111111111"}},
    )
    def test_alias_verification_success(self) -> None:
        self.service.search.return_value = [
            SimpleNamespace(
                conversion_action=SimpleNamespace(
                    resource_name="customers/0987654321/conversionActions/1111111111",
                    status=SimpleNamespace(name="ENABLED"),
                )
            )
        ]
        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            call_command("ads_verify_actions", "--alias", "lead_submit")

        output = stdout.getvalue()
        self.assertIn("[OK] Alias 'lead_submit'", output)
        self.service.search.assert_called_once()

    @override_settings(
        GADS_CUSTOMER_ID="0987654321",
        GADS_CONVERSION_ACTIONS={"lead_submit": {"id": "1111111111"}},
    )
    def test_alias_verification_strict_failure_raises(self) -> None:
        self.service.search.return_value = []
        with self.assertRaises(CommandError) as ctx:
            call_command("ads_verify_actions", "--alias", "lead_submit", "--strict")

        self.assertIn("ConversionAction not found", str(ctx.exception))

    def test_show_lists_actions(self) -> None:
        self.service.search.return_value = [
            SimpleNamespace(
                conversion_action=SimpleNamespace(
                    resource_name="customers/0987654321/conversionActions/999",
                    id="999",
                    name="Test Action",
                    status=SimpleNamespace(name="ENABLED"),
                )
            )
        ]
        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            call_command("ads_verify_actions", "--show")

        output = stdout.getvalue()
        self.assertIn("Test Action", output)
        self.assertTrue(self.service.search.called)


class AdsErrorsCommandTests(TestCase):
    def test_command_outputs_error_details(self) -> None:
        record = ConversionRecord.objects.create(
            kind=ConversionRecord.Kind.LEAD,
            action_key="lead_submit",
            idempotency_key="idem-errors",
            status=ConversionRecord.Status.ERROR,
            last_error="partial failure",
            google_upload_status={
                "error_code": "MISSING_CLICK_IDENTIFIER",
                "error_detail": "missing click identifier",
                "status_message": "partial failure",
                "errors": [
                    {
                        "code": "MISSING_CLICK_IDENTIFIER",
                        "location": "operations[0] > create",
                        "message": "Missing click id",
                    }
                ],
            },
        )

        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            call_command("ads_errors", "--limit", "5")

        output = stdout.getvalue()
        self.assertIn(f"#{record.id}", output)
        self.assertIn("code=MISSING_CLICK_IDENTIFIER", output)
        self.assertIn("MISSING_CLICK_IDENTIFIER @ operations[0]", output)

    def test_command_reports_when_no_records(self) -> None:
        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            call_command("ads_errors", "--limit", "1")

        self.assertIn("Aucune conversion", stdout.getvalue())


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
