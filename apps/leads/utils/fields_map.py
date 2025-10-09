"""Helpers to normalise FlowForms fields maps."""
from __future__ import annotations

from copy import deepcopy
from typing import Dict, Mapping

DEFAULT_FIELDS_MAP: Dict[str, str] = {
    "fullname": "full_name",
    "phone": "phone_number",
    "email": "email",
    "address_line1": "address_line1",
    "address_line2": "address_line2",
    "city": "city",
    "state": "state",
    "postal_code": "postal_code",
    "country": "country",
    "address": "address",
    "address_raw": "address",
    "quantity": "quantity",
    "offer": "offer_key",
    "pack_slug": "pack_slug",
    "product": "product",
    "promotion": "promotion_selected",
    "payment_method": "payment_method",
    "payment_mode": "payment_method",
    "bump": "bump_optin",
    "wa_optin": "wa_optin",
    "context.complementary_slugs": "context.complementary_slugs",
}

_KEY_ALIASES = {
    "full_name": "fullname",
    "phone_number": "phone",
    "payment": "payment_method",
}

_VALUE_ALIASES = {
    "payment_mode": "payment_method",
    "paymentMethod": "payment_method",
}


def _normalise_key(key: str) -> str:
    return _KEY_ALIASES.get(key, key)


def _normalise_value(value: str) -> str:
    if not value:
        return value
    return _VALUE_ALIASES.get(value, value)


def normalize_fields_map(overrides: Mapping[str, str] | None = None) -> Dict[str, str]:
    """Return a defensive copy of the fields map with required aliases patched.

    The result always contains the `payment_method` and `payment_mode` keys with the
    same value, so templates can dereference either safely.
    """

    merged = deepcopy(DEFAULT_FIELDS_MAP)

    payment_override = None

    if overrides:
        for raw_key, raw_value in overrides.items():
            if raw_value is None:
                continue
            key = _normalise_key(str(raw_key))
            value = _normalise_value(str(raw_value))
            merged[key] = value
            if key in {"payment_mode", "payment_method"} and value:
                payment_override = value

    # Ensure there is always a payment alias pair
    payment_value = payment_override or merged.get("payment_mode") or merged.get("payment_method") or "payment_method"
    merged["payment_method"] = payment_value
    merged["payment_mode"] = payment_value

    # If only a compact address field is provided, mirror it on address_line1
    if "address" in merged and merged.get("address_line1") == "address_line1":
        merged["address_line1"] = merged["address"]

    if "address_raw" in merged and merged.get("address_line1") == "address_line1":
        merged["address_line1"] = merged["address_raw"]

    return merged
