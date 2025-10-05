"""Utilities for working with Google Ads partial failures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

try:  # pragma: no cover - optional dependency
    from google.ads.googleads.client import GoogleAdsClient
    from google.ads.googleads.errors import GoogleAdsFailure  # type: ignore
except ImportError:  # pragma: no cover - library may be missing in CI
    GoogleAdsClient = object  # type: ignore
    GoogleAdsFailure = None  # type: ignore


@dataclass(frozen=True)
class PartialFailureDetail:
    """Normalised detail extracted from a Google Ads partial failure."""

    code: str
    location: str
    message: str


def _format_location(elements: Iterable[object]) -> str:
    parts: List[str] = []
    for element in elements:
        field_name = getattr(element, "field_name", "") or ""
        index = getattr(element, "index", None)
        part = field_name
        if index is not None and index >= 0:
            part = f"{part}[{index}]" if part else f"[{index}]"
        if part:
            parts.append(part)
    return " > ".join(parts)


def _derive_code(error: object) -> str:
    code_obj = getattr(error, "error_code", None)
    if code_obj is None:
        return "UNKNOWN"
    which = None
    try:
        which = code_obj.WhichOneof("error_code")
    except AttributeError:  # pragma: no cover - defensive
        which = None
    if not which:
        return "UNKNOWN"
    specific = getattr(code_obj, which, None)
    name = getattr(specific, "name", None)
    if name:
        return str(name)
    return str(which).upper()


def _load_failure_type(client: object) -> object | None:
    get_type = getattr(client, "get_type", None)
    if callable(get_type):
        try:
            return get_type("GoogleAdsFailure")
        except Exception:  # pragma: no cover - defensive
            return None
    return GoogleAdsFailure


def deserialize_partial_failure(
    client: GoogleAdsClient | object,
    status: object,
) -> List[Tuple[str, str, str]]:
    """Return ``(code, location, message)`` tuples from a partial failure status."""

    details: List[Tuple[str, str, str]] = []
    if not status:
        return details
    status_details = getattr(status, "details", None)
    if not status_details:
        return details

    failure_type = _load_failure_type(client)
    if failure_type is None:
        return details

    for any_message in status_details:
        type_url = getattr(any_message, "type_url", "")
        if type_url and not type_url.endswith("GoogleAdsFailure"):
            continue
        deserialize = getattr(failure_type, "deserialize", None)
        if not callable(deserialize):
            continue
        try:
            failure = deserialize(getattr(any_message, "value", b""))
        except Exception:  # pragma: no cover - malformed payload
            continue
        errors: Sequence[object] = getattr(failure, "errors", ())
        for error in errors:
            code = _derive_code(error)
            location = _format_location(getattr(getattr(error, "location", None), "field_path_elements", ()) or ())
            message = getattr(error, "message", "") or ""
            details.append((code or "UNKNOWN", location, message))
    return details
