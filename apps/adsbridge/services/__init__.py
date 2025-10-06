"""Service helpers for the ads bridge."""

from __future__ import annotations

import hashlib
import re
import logging
from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from django.conf import settings
from django.utils import timezone as dj_timezone

logger = logging.getLogger("adsbridge")

CONFIG_DEFAULT_PATH = Path(settings.BASE_DIR) / "configs" / "ads.yaml"


class AdsConfigError(RuntimeError):
    """Raised when the ads configuration file is missing or invalid."""


@dataclass(frozen=True)
class ConversionAction:
    key: str
    action_id: str
    type: str
    value_from: str | None = None


@dataclass(frozen=True)
class AdsConfig:
    customer_id: str
    login_customer_id: str
    default_currency: str
    conversion_actions: dict[str, ConversionAction]


@lru_cache(maxsize=1)
def load_ads_config(path: Path | None = None) -> AdsConfig:
    """Load and validate the Ads YAML mapping."""

    path = Path(path or CONFIG_DEFAULT_PATH)
    if not path.exists():
        raise AdsConfigError(f"Ads config not found at {path}")

    with path.open("r", encoding="utf-8") as handle:
        data: dict[str, Any] = yaml.safe_load(handle) or {}

    try:
        default_currency = str(data.get("default_currency", "EUR")).strip() or "EUR"
    except KeyError as exc:  # pragma: no cover - defensive branch
        raise AdsConfigError(f"Missing top-level key in ads config: {exc.args[0]}") from exc

    from apps.adsbridge.adapters.google_ads import GoogleAdsAdapter, GoogleAdsAdapterError

    try:
        resolved_credentials = GoogleAdsAdapter.load_configuration()
    except GoogleAdsAdapterError as exc:
        raise AdsConfigError(f"Unable to resolve Google Ads credentials: {exc}") from exc

    customer_id = resolved_credentials.customer_id
    login_customer_id = resolved_credentials.login_customer_id

    conversions_raw = data.get("conversion_actions") or {}
    if not isinstance(conversions_raw, dict):
        raise AdsConfigError("conversion_actions must be a mapping")

    conversion_actions: dict[str, ConversionAction] = {}
    for key, payload in conversions_raw.items():
        if not isinstance(payload, dict):
            raise AdsConfigError(f"Conversion action {key} must be a mapping")
        action_id = str(payload.get("action_id", "")).strip()
        action_type = str(payload.get("type", "")).strip() or "CLICK"
        value_from = payload.get("value_from")
        if not action_id:
            raise AdsConfigError(f"Conversion action {key} missing action_id")
        conversion_actions[key] = ConversionAction(
            key=key,
            action_id=action_id,
            type=action_type,
            value_from=str(value_from).strip() if value_from else None,
        )

    if not conversion_actions:
        raise AdsConfigError("No conversion actions configured")

    config = AdsConfig(
        customer_id=customer_id,
        login_customer_id=login_customer_id,
        default_currency=default_currency,
        conversion_actions=conversion_actions,
    )
    logger.debug("ads_config_loaded customer=%s actions=%s", customer_id, list(conversion_actions))
    return config


def get_conversion_action(key: str) -> ConversionAction:
    config = load_ads_config()
    try:
        return config.conversion_actions[key]
    except KeyError as exc:
        raise AdsConfigError(f"Unknown conversion action key: {key}") from exc


def build_idempotency_key(
    *,
    action_id: str,
    customer_id: str,
    business_reference: str,
    click_id: str | None,
    event_at: datetime,
) -> str:
    click_part = click_id or ""
    reference = business_reference or ""
    event_part = event_at.date().isoformat()
    payload = f"{customer_id}|{action_id}|{reference}|{click_part}|{event_part}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def format_event_time(dt: datetime) -> str:
    """Return the Google Ads formatted datetime (YYYY-MM-DD HH:MM:SS+HH:MM)."""

    if dj_timezone.is_naive(dt):
        dt = dj_timezone.make_aware(dt, dj_timezone.get_default_timezone())
    dt = dt.astimezone(dt_timezone.utc)
    base = dt.strftime("%Y-%m-%d %H:%M:%S")
    offset = dt.strftime("%z")
    if offset:
        offset = f"{offset[:3]}:{offset[3:]}"
    return f"{base}{offset}" if offset else base


def choose_click_identifier(record) -> tuple[str | None, str | None]:
    """Pick the preferred click identifier tuple (field, value)."""

    for field in ("gclid", "gbraid", "wbraid"):
        value = getattr(record, field, None)
        if value:
            return field, value
    return None, None


def normalize_email(email: str | None) -> str | None:
    if not email:
        return None
    email = email.strip().lower()
    if "@" not in email:
        return None
    local, domain = email.split("@", 1)
    local = local.split("+", 1)[0]
    if domain in {"gmail.com", "googlemail.com"}:
        local = local.replace(".", "")
    normalized = f"{local}@{domain}"
    return normalized or None


PHONE_CLEAN_RE = re.compile(r"[^0-9+]")


def normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    phone = PHONE_CLEAN_RE.sub("", phone)
    if not phone:
        return None
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    if not phone.startswith("+"):
        # Assume local French number if no prefix; keep last 9 digits with +33
        digits = re.sub(r"\D", "", phone)
        if len(digits) == 9:
            phone = "+33" + digits
        elif len(digits) == 10 and digits.startswith("0"):
            phone = "+33" + digits[1:]
        else:
            phone = "+" + digits
    return phone or None


def sha256_hex(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_enhanced_identifiers(
    *,
    email: str | None = None,
    phone: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> dict[str, str]:
    identifiers: dict[str, str] = {}

    normalized_email = normalize_email(email)
    if normalized_email:
        hashed_email = sha256_hex(normalized_email)
        if hashed_email:
            identifiers["hashed_email"] = hashed_email

    normalized_phone = normalize_phone(phone)
    if normalized_phone:
        hashed_phone = sha256_hex(normalized_phone)
        if hashed_phone:
            identifiers["hashed_phone"] = hashed_phone

    if first_name:
        hashed_first_name = sha256_hex(first_name.strip().lower())
        if hashed_first_name:
            identifiers["hashed_first_name"] = hashed_first_name

    if last_name:
        hashed_last_name = sha256_hex(last_name.strip().lower())
        if hashed_last_name:
            identifiers["hashed_last_name"] = hashed_last_name

    return identifiers
