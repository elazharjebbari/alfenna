from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.adsbridge.adapters.google_ads import (
    GoogleAdsAdapter,
    GoogleAdsAdapterError,
    ResolvedConfig,
)


class FakeAddressInfo:
    def __init__(self) -> None:
        self.hashed_first_name = ""
        self.hashed_last_name = ""
        self.hashed_street_address = ""
        self.postal_code = ""
        self.country_code = ""


class FakeUserIdentifier:
    def __init__(self) -> None:
        self.hashed_email = ""
        self.hashed_phone_number = ""
        self.address_info = FakeAddressInfo()
        self.user_identifier_source = None


class FakeEnums:
    class UserIdentifierSourceEnum:
        FIRST_PARTY = "FIRST_PARTY"


class FakeClient:
    def __init__(self) -> None:
        self.enums = FakeEnums()

    def get_type(self, name: str):
        if name == "UserIdentifier":
            return FakeUserIdentifier()
        raise AssertionError(f"Unexpected type request: {name}")


class AdapterUserIdentifierTests(SimpleTestCase):
    def setUp(self) -> None:
        resolved = ResolvedConfig(
            developer_token="token",
            client_id="client",
            client_secret="secret",
            refresh_token="refresh",
            login_customer_id="1234567890",
            customer_id="1234567890",
            linked_customer_id=None,
            path=Path("dummy"),
            path_exists=False,
            path_source="test",
            path_env_var=None,
            sources={"login_customer_id": "env", "customer_id": "env"},
        )
        patcher = patch(
            "apps.adsbridge.adapters.google_ads.GoogleAdsAdapter.load_configuration",
            return_value=resolved,
        )
        self.addCleanup(patcher.stop)
        patcher.start()
        self.adapter = GoogleAdsAdapter(client=FakeClient())

    def _conversion(self):
        class Conv:
            def __init__(self) -> None:
                self.user_identifiers: list[FakeUserIdentifier] = []

        return Conv()

    def test_attach_sets_email_phone_and_address(self) -> None:
        conversion = self._conversion()
        identifiers = {
            "hashed_email": "emailhash",
            "hashed_phone": "phonehash",
            "hashed_first_name": "fnamehash",
            "hashed_last_name": "lnamehash",
            "hashed_street_address": "streethash",
            "postal_code": "75001",
            "country_code": "fr",
        }

        self.adapter._attach_user_identifiers(conversion, identifiers)

        self.assertEqual(len(conversion.user_identifiers), 1)
        ui = conversion.user_identifiers[0]
        self.assertEqual(ui.hashed_email, "emailhash")
        self.assertEqual(ui.hashed_phone_number, "phonehash")
        self.assertEqual(ui.address_info.hashed_first_name, "fnamehash")
        self.assertEqual(ui.address_info.hashed_last_name, "lnamehash")
        self.assertEqual(ui.address_info.hashed_street_address, "streethash")
        self.assertEqual(ui.address_info.postal_code, "75001")
        self.assertEqual(ui.address_info.country_code, "FR")
        self.assertEqual(ui.user_identifier_source, "FIRST_PARTY")

    def test_require_customer_id_accepts_normalized_values(self) -> None:
        self.assertEqual(self.adapter._require_customer_id("123-456-7890"), "1234567890")
        self.assertEqual(self.adapter._require_customer_id(None), "1234567890")

    def test_require_customer_id_mismatch_raises(self) -> None:
        with self.assertRaises(GoogleAdsAdapterError):
            self.adapter._require_customer_id("5555555555")

    def test_require_customer_id_invalid_raises(self) -> None:
        with self.assertRaises(GoogleAdsAdapterError):
            self.adapter._require_customer_id("000-000-0000")

    def test_attach_only_address_info(self) -> None:
        conversion = self._conversion()
        identifiers = {
            "hashed_first_name": "fnamehash",
        }

        self.adapter._attach_user_identifiers(conversion, identifiers)

        self.assertEqual(len(conversion.user_identifiers), 1)
        ui = conversion.user_identifiers[0]
        self.assertEqual(ui.address_info.hashed_first_name, "fnamehash")
        self.assertEqual(ui.user_identifier_source, "FIRST_PARTY")

    def test_attach_no_data_no_identifier(self) -> None:
        conversion = self._conversion()

        self.adapter._attach_user_identifiers(conversion, {})

        self.assertEqual(conversion.user_identifiers, [])
