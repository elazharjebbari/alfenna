"""Google Ads API adapter."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from decimal import Decimal
from functools import cached_property
from pathlib import Path
from typing import Any, Iterable

import yaml
from django.conf import settings

from apps.adsbridge import services
from apps.adsbridge.services.actions import resolve_conversion_action

from .errors import deserialize_partial_failure

logger = logging.getLogger("adsbridge.adapter")

try:  # pragma: no cover - optional dependency
    from google.ads.googleads.client import GoogleAdsClient
    from google.ads.googleads.errors import GoogleAdsException
except ImportError:  # pragma: no cover - library not installed in some environments
    GoogleAdsClient = None  # type: ignore

    class GoogleAdsException(Exception):  # type: ignore
        pass


class GoogleAdsAdapterError(RuntimeError):
    """Base adapter exception."""


class GoogleAdsTransientError(GoogleAdsAdapterError):
    """Transient failure; caller should retry."""


class GoogleAdsDuplicateError(GoogleAdsAdapterError):
    """Duplicate conversion; treat as already processed."""


class GoogleAdsPartialFailureError(GoogleAdsAdapterError):
    """Raised when Google Ads returns a partial failure payload."""

    def __init__(
        self,
        message: str,
        *,
        codes: str,
        errors: list[dict[str, str]],
        status_message: str | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = codes or "UNKNOWN"
        self.error_detail = message
        self.partial_failure_errors = errors
        if status_message:
            self.partial_failure_status_message = status_message


class GoogleAdsActionNotFoundError(GoogleAdsAdapterError):
    """Raised when the configured conversion action cannot be resolved."""

    def __init__(
        self,
        resource_name: str,
        *,
        alias: str | None = None,
        status: str | None = None,
        customer_id: str | None = None,
    ) -> None:
        detail_parts = [f"resource={resource_name}"]
        if alias and alias != resource_name:
            detail_parts.append(f"alias={alias}")
        if customer_id:
            detail_parts.append(f"customer={customer_id}")
        if status:
            detail_parts.append(f"status={status}")
        message = "ACTION_NOT_FOUND: " + " ".join(detail_parts)
        super().__init__(message)
        self.resource_name = resource_name
        self.alias = alias
        self.status = status
        self.customer_id = customer_id


@dataclass(frozen=True)
class UploadResult:
    status: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class ResolvedConfig:
    developer_token: str
    client_id: str
    client_secret: str
    refresh_token: str
    login_customer_id: str
    customer_id: str
    linked_customer_id: str | None
    path: Path
    path_exists: bool
    path_source: str
    path_env_var: str | None
    sources: dict[str, str]


class GoogleAdsAdapter:
    """Thin wrapper around the Google Ads upload services."""

    ACTION_CACHE_TTL_SECONDS = 300
    DEFAULT_CONFIG_PATH = Path(settings.BASE_DIR) / "credentials" / "google-ads.yaml"

    def __init__(
        self,
        *,
        validate_only: bool | None = None,
        partial_failure: bool | None = None,
        configuration_path: str | os.PathLike[str] | None = None,
        client: GoogleAdsClient | None = None,
    ) -> None:
        resolved = self.load_configuration(configuration_path)
        self._resolved_config = resolved
        self._customer_id = resolved.customer_id
        self._login_customer_id = resolved.login_customer_id

        if client is not None:
            self._client = client
        else:
            if GoogleAdsClient is None:
                raise GoogleAdsAdapterError("google-ads library is not installed")
            client_payload = {
                "developer_token": resolved.developer_token,
                "client_id": resolved.client_id,
                "client_secret": resolved.client_secret,
                "refresh_token": resolved.refresh_token,
                "login_customer_id": resolved.login_customer_id,
                "use_proto_plus": True,
            }
            if resolved.linked_customer_id:
                client_payload["linked_customer_id"] = resolved.linked_customer_id
            try:
                self._client = GoogleAdsClient.load_from_dict(client_payload)
            except Exception as exc:  # pragma: no cover - library specific
                raise GoogleAdsAdapterError(f"Unable to initialise Google Ads client: {exc}") from exc

        self._client.login_customer_id = resolved.login_customer_id

        self.validate_only = (
            settings.GADS_VALIDATE_ONLY if validate_only is None else bool(validate_only)
        )
        self.partial_failure = (
            settings.GADS_PARTIAL_FAILURE if partial_failure is None else bool(partial_failure)
        )

        self._conversion_action_cache: dict[str, tuple[float, str]] = {}

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------
    @classmethod
    def load_configuration(
        cls, configuration_path: str | os.PathLike[str] | None = None
    ) -> ResolvedConfig:
        path_source = "argument"
        path_env_var: str | None = None
        if configuration_path:
            path = Path(configuration_path)
        else:
            env_override = os.getenv("GADS_CONFIGURATION_PATH")
            if env_override:
                path = Path(env_override)
                path_source = "env"
                path_env_var = "GADS_CONFIGURATION_PATH"
            else:
                configured_path = getattr(settings, "GADS_CONFIGURATION_PATH", None)
                if configured_path:
                    path = Path(configured_path)
                    path_source = (
                        "default"
                        if Path(configured_path) == cls.DEFAULT_CONFIG_PATH
                        else "settings"
                    )
                else:
                    path = cls.DEFAULT_CONFIG_PATH
                    path_source = "default"
        yaml_payload: dict[str, Any] = {}
        path_exists = path.exists()
        if path_exists:
            try:
                yaml_payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception as exc:  # pragma: no cover - invalid file
                raise GoogleAdsAdapterError(f"Unable to read Google Ads configuration: {exc}") from exc
        if not isinstance(yaml_payload, dict):
            raise GoogleAdsAdapterError("Google Ads configuration must be a mapping")
        cleaned_yaml: dict[str, Any] = {}
        for raw_key, raw_value in yaml_payload.items():
            if raw_value is None:
                continue
            key = raw_key.strip() if isinstance(raw_key, str) else raw_key
            cleaned_yaml[key] = raw_value
        yaml_payload = cleaned_yaml

        sources: dict[str, str] = {}
        resolved: dict[str, Any] = {}

        for key in (
            "developer_token",
            "client_id",
            "client_secret",
            "refresh_token",
            "login_customer_id",
            "customer_id",
            "linked_customer_id",
        ):
            env_key = f"GADS_{key.upper()}"
            env_value = os.getenv(env_key)
            env_marker = ""
            cleaned_env = cls._clean_value(key, env_value)
            if env_value is not None and not cleaned_env:
                env_marker = f"env_invalid:{env_key}"
            if cleaned_env:
                resolved[key] = cleaned_env
                sources[key] = f"env:{env_key}"
                continue
            yaml_value = yaml_payload.get(key)
            cleaned_yaml = cls._clean_value(key, yaml_value)
            if cleaned_yaml:
                resolved[key] = cleaned_yaml
                sources[key] = "yaml" if not env_marker else f"yaml ({env_marker})"
            else:
                resolved[key] = None
                sources[key] = env_marker or "missing"

        for required_key in ("developer_token", "client_id", "client_secret", "refresh_token"):
            if not resolved.get(required_key):
                raise GoogleAdsAdapterError(
                    f"Google Ads configuration missing {required_key}"
                )

        login_customer_id = cls._normalize_customer_id(resolved.get("login_customer_id"))
        customer_id = cls._normalize_customer_id(resolved.get("customer_id"))
        if not login_customer_id or not customer_id:
            raise GoogleAdsAdapterError("Missing or invalid customer ids")

        linked_customer_id = cls._normalize_customer_id(resolved.get("linked_customer_id"))

        return ResolvedConfig(
            developer_token=str(resolved["developer_token"]),
            client_id=str(resolved["client_id"]),
            client_secret=str(resolved["client_secret"]),
            refresh_token=str(resolved["refresh_token"]),
            login_customer_id=login_customer_id,
            customer_id=customer_id,
            linked_customer_id=linked_customer_id,
            path=path,
            path_exists=path_exists,
            path_source=path_source,
            path_env_var=path_env_var,
            sources=sources,
        )

    @staticmethod
    def _clean_value(key: str, value: Any) -> str | None:
        if value is None:
            return None
        if key in {"login_customer_id", "customer_id", "linked_customer_id"}:
            return GoogleAdsAdapter._normalize_customer_id(value)
        text = str(value).strip()
        return text or None

    @staticmethod
    def _normalize_customer_id(value: Any) -> str | None:
        if value is None:
            return None
        digits = re.sub(r"\D", "", str(value))
        if len(digits) != 10 or set(digits) == {"0"}:
            return None
        return digits

    @property
    def customer_id(self) -> str:
        return self._customer_id

    @property
    def login_customer_id(self) -> str:
        return self._login_customer_id

    @property
    def configuration_metadata(self) -> dict[str, Any]:
        return {
            "path": str(self._resolved_config.path),
            "path_exists": self._resolved_config.path_exists,
            "path_source": self._resolved_config.path_source,
            "path_env_var": self._resolved_config.path_env_var,
            "sources": dict(self._resolved_config.sources),
        }

    # ------------------------------------------------------------------
    # Google Ads service helpers
    # ------------------------------------------------------------------
    @cached_property
    def enums(self):
        return self._client.enums

    @cached_property
    def conversion_upload_service(self):
        return self._client.get_service("ConversionUploadService")

    @cached_property
    def conversion_adjustment_upload_service(self):
        return self._client.get_service("ConversionAdjustmentUploadService")

    @cached_property
    def google_ads_service(self):
        return self._client.get_service("GoogleAdsService")

    @cached_property
    def conversion_action_service(self):
        return self._client.get_service("ConversionActionService")

    def upload_click_conversion(
        self,
        *,
        customer_id: str,
        action_id: str,
        click_id_field: str | None,
        click_id: str | None,
        value: Decimal | float | None,
        currency: str | None,
        order_id: str | None,
        event_at,
        enhanced_identifiers: dict[str, str] | None = None,
    ) -> UploadResult:
        normalized_customer_id = self._require_customer_id(customer_id)

        resource_name = self._conversion_action_resource(
            normalized_customer_id, action_id
        )
        conversion = self._client.get_type("ClickConversion")
        conversion.conversion_action = resource_name
        if click_id_field and click_id:
            setattr(conversion, click_id_field, click_id)
        conversion.conversion_date_time = services.format_event_time(event_at)

        if value is not None:
            conversion.value = float(value)
        if currency:
            conversion.currency_code = currency
        if order_id:
            conversion.order_id = order_id

        if enhanced_identifiers:
            self._attach_user_identifiers(conversion, enhanced_identifiers)

        logger.debug(
            "ads_click_upload payload=%s",
            json.dumps(
                {
                    "customer_id": normalized_customer_id,
                    "action_id": action_id,
                    "click_id_field": click_id_field,
                    "has_identifiers": bool(enhanced_identifiers),
                }
            ),
        )

        request = {
            "customer_id": normalized_customer_id,
            "conversions": [conversion],
        }
        if self.partial_failure is not None:
            request["partial_failure"] = self.partial_failure
        if self.validate_only is not None:
            request["validate_only"] = self.validate_only
        try:
            response = self.conversion_upload_service.upload_click_conversions(request=request)
        except GoogleAdsException as exc:  # pragma: no cover - library specific
            self._raise_from_exception(exc)

        self._handle_partial_failure(response)

        first_result = response.results[0] if response.results else None
        payload = {
            "resource_name": getattr(first_result, "resource_name", None),
            "validate_only": self.validate_only,
        }
        return UploadResult(status="OK", payload=payload)

    def upload_adjustment(
        self,
        *,
        customer_id: str,
        action_id: str,
        order_id: str,
        adjustment_type: str,
        event_at,
        adjusted_value: Decimal | float | None = None,
        currency: str | None = None,
    ) -> UploadResult:
        normalized_customer_id = self._require_customer_id(customer_id)

        resource_name = self._conversion_action_resource(
            normalized_customer_id, action_id
        )
        adjustment = self._client.get_type("ConversionAdjustment")
        adjustment.conversion_action = resource_name
        adjustment.order_id = order_id
        adjustment.adjustment_date_time = services.format_event_time(event_at)
        adjustment.adjustment_type = self._map_adjustment_type(adjustment_type)

        if adjusted_value is not None:
            restatement = adjustment.restatement_value
            restatement.adjusted_value = float(adjusted_value)
            if currency:
                restatement.currency_code = currency

        logger.debug(
            "ads_adjustment_upload payload=%s",
            json.dumps(
                {
                    "customer_id": customer_id,
                    "action_id": action_id,
                    "order_id": order_id,
                    "adjustment_type": adjustment_type,
                }
            ),
        )

        request = {
            "customer_id": normalized_customer_id,
            "conversion_adjustments": [adjustment],
        }
        if self.partial_failure is not None:
            request["partial_failure"] = self.partial_failure
        if self.validate_only is not None:
            request["validate_only"] = self.validate_only
        try:
            response = self.conversion_adjustment_upload_service.upload_conversion_adjustments(request=request)
        except GoogleAdsException as exc:  # pragma: no cover - library specific
            self._raise_from_exception(exc)

        self._handle_partial_failure(response)

        first_result = response.results[0] if response.results else None
        payload = {
            "resource_name": getattr(first_result, "resource_name", None),
            "validate_only": self.validate_only,
        }
        return UploadResult(status="OK", payload=payload)

    # --- internal helpers -------------------------------------------------

    def _conversion_action_resource(self, customer_id: str, action_id: str) -> str:
        try:
            resource_name = resolve_conversion_action(action_id, customer_id=customer_id)
        except ValueError as exc:
            raise GoogleAdsAdapterError(str(exc)) from exc
        self._preverify_conversion_action(resource_name, alias=str(action_id))
        return resource_name

    def _preverify_conversion_action(self, resource_name: str, *, alias: str | None = None) -> None:
        if not settings.GADS_PREVERIFY_ACTIONS:
            return

        now = time.monotonic()
        cached = self._conversion_action_cache.get(resource_name)
        status: str | None = None
        if cached and (now - cached[0]) < self.ACTION_CACHE_TTL_SECONDS:
            status = cached[1]
        else:
            query = (
                "SELECT conversion_action.status "
                "FROM conversion_action "
                f"WHERE conversion_action.resource_name = '{resource_name}'"
            )
            try:
                rows = list(
                    self.google_ads_service.search(
                        customer_id=self.customer_id,
                        query=query,
                    )
                )
            except GoogleAdsException as exc:  # pragma: no cover - API failure path
                self._raise_from_exception(exc)
            if not rows:
                status = "NOT_FOUND"
            else:
                status_obj = getattr(rows[0].conversion_action, "status", None)
                status = getattr(status_obj, "name", str(status_obj)) if status_obj else "UNKNOWN"
            self._conversion_action_cache[resource_name] = (now, status or "UNKNOWN")

        if status != "ENABLED":
            raise GoogleAdsActionNotFoundError(
                resource_name,
                alias=alias,
                status=status,
                customer_id=self.customer_id,
            )

    def _require_customer_id(self, provided: str | None) -> str:
        normalized = self._normalize_customer_id(provided or self._customer_id)
        if not normalized:
            raise GoogleAdsAdapterError("Missing or invalid customer id")
        if normalized != self._customer_id:
            raise GoogleAdsAdapterError("Customer id mismatch with configuration")
        return normalized

    def _attach_user_identifiers(self, conversion, identifiers: dict[str, str]) -> None:
        if not identifiers:
            return

        user_identifier = self._client.get_type("UserIdentifier")
        has_data = False

        email = identifiers.get("hashed_email")
        if email:
            user_identifier.hashed_email = email
            has_data = True

        phone = identifiers.get("hashed_phone") or identifiers.get("hashed_phone_number")
        if phone:
            user_identifier.hashed_phone_number = phone
            has_data = True

        address_info = getattr(user_identifier, "address_info", None)
        if address_info is not None:
            mapping = {
                "hashed_first_name": "hashed_first_name",
                "hashed_last_name": "hashed_last_name",
                "hashed_street_address": "hashed_street_address",
                "postal_code": "postal_code",
                "country_code": "country_code",
            }
            for source_key, target_attr in mapping.items():
                value = identifiers.get(source_key)
                if not value:
                    continue
                if target_attr == "country_code":
                    value = str(value).upper()
                setattr(address_info, target_attr, value)
                has_data = True

        if has_data:
            user_identifier.user_identifier_source = self.enums.UserIdentifierSourceEnum.FIRST_PARTY
            conversion.user_identifiers.extend([user_identifier])

    def _handle_partial_failure(self, response) -> None:
        failure_status = getattr(response, "partial_failure_error", None)
        if not failure_status:
            return

        client = getattr(self, "_client", None)
        details = deserialize_partial_failure(client or object(), failure_status)
        if not details:
            message = getattr(failure_status, "message", "") or "partial failure"
            logger.error("google_ads_partial_failure_no_details message=%s", message)
            if "duplicate" in message.lower():
                raise GoogleAdsDuplicateError(message)
            raise GoogleAdsAdapterError(message)

        codes = sorted({code for code, _, _ in details if code})
        codes_str = ",".join(codes) if codes else "UNKNOWN"
        status_message = getattr(failure_status, "message", "") or ""

        errors_payload = [
            {"code": code, "location": location, "message": msg}
            for code, location, msg in details
        ]

        logger.error(
            "google_ads_partial_failure codes=%s status=%s errors=%s",
            codes_str,
            status_message,
            errors_payload,
        )

        duplicate_codes = {"DUPLICATE_CONVERSION", "CONVERSION_ALREADY_RETRACTED"}
        first_error = errors_payload[0]
        first_message = first_error["message"] or status_message or "partial failure"
        summary_message = (
            f"partial failure: codes={codes_str}; "
            f"first={first_error['code']} at {first_error['location'] or 'n/a'}: {first_message}"
        )

        if any(code in duplicate_codes for code in {item["code"] for item in errors_payload}):
            duplicate_exc = GoogleAdsDuplicateError(summary_message)
            duplicate_exc.error_code = codes_str
            duplicate_exc.error_detail = summary_message
            duplicate_exc.partial_failure_errors = errors_payload
            if status_message:
                duplicate_exc.partial_failure_status_message = status_message
            raise duplicate_exc

        raise GoogleAdsPartialFailureError(
            summary_message,
            codes=codes_str,
            errors=errors_payload,
            status_message=status_message,
        )

    def _map_adjustment_type(self, adjustment_type: str):
        mapping = {
            "RESTATEMENT": self.enums.ConversionAdjustmentTypeEnum.RESTATEMENT,
            "RETRACTION": self.enums.ConversionAdjustmentTypeEnum.RETRACTION,
            "ENHANCEMENT": self.enums.ConversionAdjustmentTypeEnum.ENHANCEMENT,
        }
        key = (adjustment_type or "").upper()
        if key not in mapping:
            raise GoogleAdsAdapterError(f"Unsupported adjustment type: {adjustment_type}")
        return mapping[key]

    def _raise_from_exception(self, exc: GoogleAdsException) -> None:
        status_code = None
        if hasattr(exc, "error") and exc.error is not None:
            try:
                status_code = exc.error.code().name
            except Exception:  # pragma: no cover - guard
                status_code = None
        errors = list(getattr(exc.failure, "errors", [])) if hasattr(exc, "failure") else []
        if errors:
            if any(self._is_duplicate_error(err) for err in errors):
                raise GoogleAdsDuplicateError(self._errors_to_message(errors)) from exc
            if any(self._is_transient_error(err) for err in errors):
                raise GoogleAdsTransientError(self._errors_to_message(errors)) from exc
        if status_code in {"UNAVAILABLE", "DEADLINE_EXCEEDED", "RESOURCE_EXHAUSTED"}:
            raise GoogleAdsTransientError(status_code or "transient error") from exc
        raise GoogleAdsAdapterError(self._errors_to_message(errors) or str(exc)) from exc

    def _is_duplicate_error(self, error) -> bool:
        code_obj = getattr(error.error_code, "conversion_upload_error", None)
        if code_obj and getattr(code_obj, "name", str(code_obj)) in {"DUPLICATE_CONVERSION", "CONVERSION_ALREADY_RETRACTED"}:
            return True
        adj_code = getattr(error.error_code, "conversion_adjustment_upload_error", None)
        if adj_code and getattr(adj_code, "name", str(adj_code)) in {
            "CONVERSION_ALREADY_ENHANCED",
            "CONVERSION_ALREADY_RETRACTED",
        }:
            return True
        return False

    def _is_transient_error(self, error) -> bool:
        for attr_name in (
            "internal_error",
            "quota_error",
            "transient_error",
        ):
            code_obj = getattr(error.error_code, attr_name, None)
            if code_obj and getattr(code_obj, "name", "").upper() in {"INTERNAL_ERROR", "RESOURCE_EXHAUSTED", "TRANSIENT_ERROR"}:
                return True
        return False

    @staticmethod
    def _errors_to_message(errors: Iterable[Any]) -> str:
        messages = []
        for error in errors:
            detail = getattr(error, "message", "")
            code_repr = str(getattr(error, "error_code", ""))
            messages.append(f"{code_repr} {detail}".strip())
        return "; ".join(messages)


class MockGoogleAdsAdapter:
    """Adapter returning mock responses without calling Google Ads."""

    def __init__(self, resolved: ResolvedConfig | None = None) -> None:
        self._resolved_config = resolved or GoogleAdsAdapter.load_configuration()
        self._customer_id = self._resolved_config.customer_id
        self._login_customer_id = self._resolved_config.login_customer_id

    @property
    def customer_id(self) -> str:
        return self._customer_id

    @property
    def login_customer_id(self) -> str:
        return self._login_customer_id

    @property
    def configuration_metadata(self) -> dict[str, Any]:
        return {
            "path": str(self._resolved_config.path),
            "path_exists": self._resolved_config.path_exists,
            "path_source": self._resolved_config.path_source,
            "path_env_var": self._resolved_config.path_env_var,
            "sources": dict(self._resolved_config.sources),
        }

    def upload_click_conversion(
        self,
        *,
        customer_id: str,
        action_id: str,
        click_id_field: str | None,
        click_id: str | None,
        value: Decimal | float | None,
        currency: str | None,
        order_id: str | None,
        event_at,
        enhanced_identifiers: dict[str, str] | None = None,
    ) -> UploadResult:
        payload = {
            "resource_name": f"mock/{customer_id}/{action_id}",
            "mode": "mock",
            "click_id_field": click_id_field,
            "has_identifiers": bool(enhanced_identifiers),
        }
        return UploadResult(status="MOCK", payload=payload)

    def upload_adjustment(
        self,
        *,
        customer_id: str,
        action_id: str,
        order_id: str,
        adjustment_type: str,
        event_at,
        adjusted_value: Decimal | float | None = None,
        currency: str | None = None,
    ) -> UploadResult:
        payload = {
            "resource_name": f"mock-adjust/{customer_id}/{action_id}",
            "mode": "mock",
            "order_id": order_id,
            "adjustment_type": adjustment_type,
        }
        return UploadResult(status="MOCK", payload=payload)
