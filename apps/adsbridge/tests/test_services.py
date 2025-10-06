from __future__ import annotations

import hashlib
import os
import tempfile
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from django.utils import timezone

from apps.adsbridge import services
from apps.adsbridge.adapters.google_ads import ResolvedConfig


class AdsServicesTests(SimpleTestCase):
    def setUp(self) -> None:
        services.load_ads_config.cache_clear()
        self.env_patch = patch.dict(
            os.environ,
            {"GADS_CUSTOMER_ID": "", "GADS_LOGIN_CUSTOMER_ID": ""},
            clear=False,
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

        self.default_resolved = self._resolved_config(
            customer_id="1234567890", login_customer_id="9876543210"
        )
        patcher = patch(
            "apps.adsbridge.adapters.google_ads.GoogleAdsAdapter.load_configuration",
            return_value=self.default_resolved,
        )
        self.load_configuration_mock = patcher.start()
        self.addCleanup(patcher.stop)

    def _resolved_config(
        self,
        *,
        customer_id: str,
        login_customer_id: str,
        path: str = "cred.yaml",
        path_source: str = "default",
        path_env_var: str | None = None,
    ) -> ResolvedConfig:
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
            login_customer_id=login_customer_id,
            customer_id=customer_id,
            linked_customer_id=None,
            path=Path(path),
            path_exists=True,
            path_source=path_source,
            path_env_var=path_env_var,
            sources=sources,
        )

    def _write_config(self, content: str) -> Path:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
        tmp.write(content)
        tmp.flush()
        tmp.close()
        path = Path(tmp.name)
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        return path

    def test_load_ads_config_parses_conversion_actions(self) -> None:
        config_path = self._write_config(
            """
default_currency: "EUR"
conversion_actions:
  lead_submit:
    action_id: "111"
    type: "CLICK"
  purchase:
    action_id: "222"
    type: "CLICK"
    value_from: "order.total"
"""
        )
        cfg = services.load_ads_config(config_path)
        self.assertEqual(cfg.customer_id, "1234567890")
        self.assertEqual(cfg.login_customer_id, "9876543210")
        self.assertEqual(cfg.default_currency, "EUR")
        self.assertIn("lead_submit", cfg.conversion_actions)
        self.assertEqual(cfg.conversion_actions["purchase"].value_from, "order.total")

    def test_load_ads_config_uses_resolved_credentials(self) -> None:
        config_path = self._write_config(
            """
conversion_actions:
  lead_submit:
    action_id: "111"
    type: "CLICK"
"""
        )
        self.load_configuration_mock.return_value = self._resolved_config(
            customer_id="0001112222",
            login_customer_id="3334445555",
        )
        services.load_ads_config.cache_clear()
        cfg = services.load_ads_config(config_path)
        self.assertEqual(cfg.customer_id, "0001112222")
        self.assertEqual(cfg.login_customer_id, "3334445555")

    def test_load_ads_config_credentials_error_propagates(self) -> None:
        config_path = self._write_config(
            """
conversion_actions:
  lead_submit:
    action_id: "111"
    type: "CLICK"
"""
        )
        services.load_ads_config.cache_clear()
        from apps.adsbridge.adapters.google_ads import GoogleAdsAdapterError

        self.load_configuration_mock.side_effect = GoogleAdsAdapterError("boom")
        with self.assertRaises(services.AdsConfigError) as ctx:
            services.load_ads_config(config_path)
        self.assertIn("Unable to resolve Google Ads credentials", str(ctx.exception))

    def test_build_idempotency_key_stable(self) -> None:
        key1 = services.build_idempotency_key(
            action_id="111",
            customer_id="123",
            business_reference="order-1",
            click_id="abc",
            event_at=datetime(2024, 10, 1, 12, 0, 0),
        )
        key2 = services.build_idempotency_key(
            action_id="111",
            customer_id="123",
            business_reference="order-1",
            click_id="abc",
            event_at=datetime(2024, 10, 1, 22, 0, 0),
        )
        self.assertEqual(key1, key2)
        self.assertEqual(key1, hashlib.sha1(b"123|111|order-1|abc|2024-10-01").hexdigest())

    def test_build_enhanced_identifiers_hashes_values(self) -> None:
        identifiers = services.build_enhanced_identifiers(
            email="Alice.Example+test@gmail.com",
            phone="06 12 34 56 78",
            first_name="Alice",
            last_name="Example",
        )
        expected_email = hashlib.sha256(b"aliceexample@gmail.com").hexdigest()
        expected_phone = hashlib.sha256(b"+33612345678").hexdigest()
        self.assertEqual(identifiers["hashed_email"], expected_email)
        self.assertEqual(identifiers["hashed_phone"], expected_phone)
        self.assertEqual(identifiers["hashed_first_name"], hashlib.sha256(b"alice").hexdigest())
        self.assertEqual(identifiers["hashed_last_name"], hashlib.sha256(b"example").hexdigest())

    def test_load_ads_config_missing_file_raises(self) -> None:
        with self.assertRaises(services.AdsConfigError):
            services.load_ads_config(Path("/tmp/does-not-exist.yaml"))
