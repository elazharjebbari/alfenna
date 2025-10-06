from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from apps.adsbridge.services.actions import (
    RESOURCE_RE,
    build_resource_name,
    resolve_conversion_action,
)


class ConversionActionResolverTests(SimpleTestCase):
    @override_settings(GADS_CUSTOMER_ID="1234567890")
    def test_build_resource_name_sanitizes_inputs(self) -> None:
        resource = build_resource_name("123-456-7890", " 9876543210 ")
        self.assertEqual(resource, "customers/1234567890/conversionActions/9876543210")

    def test_build_resource_name_requires_numeric_ids(self) -> None:
        with self.assertRaisesMessage(
            ValueError, "Conversion action customer_id is required"
        ):
            build_resource_name("", "111")
        with self.assertRaisesMessage(ValueError, "Conversion action id must be numeric"):
            build_resource_name("1234567890", "not-a-number")

    @override_settings(GADS_CUSTOMER_ID="1234567890")
    def test_resolve_accepts_resource_name(self) -> None:
        resource = "customers/1234567890/conversionActions/1111111111"
        self.assertRegex(resource, RESOURCE_RE.pattern)
        self.assertEqual(resolve_conversion_action(resource), resource)

    @override_settings(GADS_CUSTOMER_ID="1234567890")
    def test_resolve_numeric_id(self) -> None:
        resource = resolve_conversion_action("9876543210")
        self.assertEqual(resource, "customers/1234567890/conversionActions/9876543210")

    @override_settings(
        GADS_CUSTOMER_ID="1234567890",
        GADS_CONVERSION_ACTIONS={"lead_submit": {"id": "1112223334"}},
    )
    def test_resolve_alias_uses_mapping_id(self) -> None:
        resource = resolve_conversion_action("lead_submit")
        self.assertEqual(resource, "customers/1234567890/conversionActions/1112223334")

    @override_settings(
        GADS_CONVERSION_ACTIONS={
            "lead_submit": {
                "resource_name": "customers/9999999999/conversionActions/1112223334",
            }
        }
    )
    def test_resolve_alias_with_resource_name_returns_value(self) -> None:
        resource = resolve_conversion_action("lead_submit")
        self.assertEqual(
            resource, "customers/9999999999/conversionActions/1112223334"
        )

    @override_settings(GADS_CUSTOMER_ID="")
    def test_resolve_numeric_requires_customer_id(self) -> None:
        with self.assertRaisesMessage(
            ValueError, "Conversion action customer_id is required"
        ):
            resolve_conversion_action("1234567890")

    def test_resolve_unknown_alias(self) -> None:
        with self.assertRaisesMessage(
            ValueError, "Cannot resolve conversion_action from 'unknown_alias'"
        ):
            resolve_conversion_action("unknown_alias")
