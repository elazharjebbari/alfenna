from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.adsbridge.adapters.google_ads import GoogleAdsAdapter, GoogleAdsAdapterError


class AdapterConfigurationTests(SimpleTestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.config_path = Path(self.tmpdir.name) / "google-ads.yaml"
        self.base_yaml = (
            "developer_token: token\n"
            "client_id: client\n"
            "client_secret: secret\n"
            "refresh_token: refresh\n"
            "login_customer_id: 123-456-7890\n"
            "customer_id: 098-765-4321\n"
        )

    def _write_config(self, content: str | None = None) -> None:
        self.config_path.write_text(content or self.base_yaml, encoding="utf-8")

    def _override_env(self, customer: str, login: str, *, path: str = ""):
        return patch.dict(
            os.environ,
            {
                "GADS_DEVELOPER_TOKEN": "",
                "GADS_CLIENT_ID": "",
                "GADS_CLIENT_SECRET": "",
                "GADS_REFRESH_TOKEN": "",
                "GADS_LINKED_CUSTOMER_ID": "",
                "GADS_CUSTOMER_ID": customer,
                "GADS_LOGIN_CUSTOMER_ID": login,
                "GADS_CONFIGURATION_PATH": path,
            },
            clear=False,
        )

    def test_load_configuration_from_yaml(self) -> None:
        self._write_config()
        with override_settings(GADS_CONFIGURATION_PATH=str(self.config_path)):
            with self._override_env("", ""):
                resolved = GoogleAdsAdapter.load_configuration()
        self.assertEqual(resolved.customer_id, "0987654321")
        self.assertEqual(resolved.login_customer_id, "1234567890")
        self.assertTrue(resolved.sources["customer_id"].startswith("yaml"))
        self.assertTrue(resolved.sources["login_customer_id"].startswith("yaml"))
        self.assertEqual(resolved.path_source, "settings")
        self.assertIsNone(resolved.path_env_var)

    def test_load_configuration_env_override(self) -> None:
        self._write_config()
        with override_settings(GADS_CONFIGURATION_PATH=str(self.config_path)):
            with self._override_env("111-222-3333", "444-555-6666"):
                resolved = GoogleAdsAdapter.load_configuration()
        self.assertEqual(resolved.customer_id, "1112223333")
        self.assertEqual(resolved.login_customer_id, "4445556666")
        self.assertEqual(resolved.sources["customer_id"], "env:GADS_CUSTOMER_ID")
        self.assertEqual(
            resolved.sources["login_customer_id"], "env:GADS_LOGIN_CUSTOMER_ID"
        )

    def test_load_configuration_missing_ids_raises(self) -> None:
        yaml_content = (
            "developer_token: token\n"
            "client_id: client\n"
            "client_secret: secret\n"
            "refresh_token: refresh\n"
        )
        self._write_config(yaml_content)
        with override_settings(GADS_CONFIGURATION_PATH=str(self.config_path)):
            with self._override_env("", ""):
                with self.assertRaises(GoogleAdsAdapterError):
                    GoogleAdsAdapter.load_configuration()

    def test_load_configuration_rejects_placeholder_ids(self) -> None:
        yaml_content = (
            "developer_token: token\n"
            "client_id: client\n"
            "client_secret: secret\n"
            "refresh_token: refresh\n"
            "login_customer_id: 000-000-0000\n"
            "customer_id: 0000000000\n"
        )
        self._write_config(yaml_content)
        with override_settings(GADS_CONFIGURATION_PATH=str(self.config_path)):
            with self._override_env("", ""):
                with self.assertRaises(GoogleAdsAdapterError):
                    GoogleAdsAdapter.load_configuration()

    def test_load_configuration_trims_yaml_keys(self) -> None:
        yaml_content = (
            "developer_token : token\n"
            "client_id: client\n"
            "client_secret: secret\n"
            "refresh_token : refresh\n"
            "login_customer_id: 123-456-7890\n"
            "customer_id: 098-765-4321\n"
        )
        self._write_config(yaml_content)
        with override_settings(GADS_CONFIGURATION_PATH=str(self.config_path)):
            with self._override_env("", ""):
                resolved = GoogleAdsAdapter.load_configuration()
        self.assertEqual(resolved.refresh_token, "refresh")
        self.assertTrue(resolved.sources["refresh_token"].startswith("yaml"))
