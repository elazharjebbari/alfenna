"""Helpers for resolving Google Ads conversion actions."""

from __future__ import annotations

import re
from typing import Any, Mapping

from django.conf import settings

RESOURCE_RE = re.compile(r"^customers/\d+/conversionActions/\d+$")


def build_resource_name(customer_id: str | int, action_id: str | int) -> str:
    """Return a sanitized conversion action resource name."""

    cid = _only_digits(customer_id)
    aid = _only_digits(action_id)
    if not cid:
        raise ValueError("Conversion action customer_id is required")
    if not aid:
        raise ValueError("Conversion action id must be numeric")
    return f"customers/{cid}/conversionActions/{aid}"


def resolve_conversion_action(
    alias_or_id_or_resource: str | int, *, customer_id: str | int | None = None
) -> str:
    """Resolve conversion action alias/id/resource into a resource name."""

    candidate = str(alias_or_id_or_resource or "").strip()
    if not candidate:
        raise ValueError("Conversion action identifier is required")
    if RESOURCE_RE.fullmatch(candidate):
        return candidate

    mapping: Mapping[str, Mapping[str, Any]] = getattr(settings, "GADS_CONVERSION_ACTIONS", {}) or {}
    default_customer = customer_id if customer_id is not None else getattr(settings, "GADS_CUSTOMER_ID", "")
    if candidate in mapping:
        entry = mapping[candidate]
        if not isinstance(entry, Mapping):
            raise ValueError(f"Conversion action mapping for '{candidate}' must be a mapping")
        resource_name = _value(entry, "resource_name")
        if resource_name:
            if RESOURCE_RE.fullmatch(resource_name):
                return resource_name
            raise ValueError(f"Invalid conversion action resource name configured for '{candidate}'")
        action_id = _value(entry, "id")
        if not action_id:
            raise ValueError(f"Conversion action mapping for '{candidate}' missing id/resource_name")
        resolved_customer = _value(entry, "customer_id") or default_customer
        return build_resource_name(resolved_customer, action_id)

    try:
        from apps.adsbridge import services as adsbridge_services

        config_action = adsbridge_services.get_conversion_action(candidate)
    except Exception:
        config_action = None
    if config_action and getattr(config_action, "action_id", None):
        return build_resource_name(default_customer, config_action.action_id)

    if candidate.isdigit():
        return build_resource_name(default_customer, candidate)

    raise ValueError(f"Cannot resolve conversion_action from '{candidate}'")


def _only_digits(value: str | int | None) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _value(entry: Mapping[str, Any], key: str) -> str:
    value = entry.get(key)
    if value is None:
        return ""
    return str(value).strip()
