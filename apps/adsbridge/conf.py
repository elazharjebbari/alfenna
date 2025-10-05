"""Runtime helpers for the Ads S2S feature flags."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from django.conf import settings

AdsMode = Literal["off", "capture", "on", "mock"]

_VALID_MODES: set[str] = {"off", "capture", "on", "mock"}


def current_mode() -> AdsMode:
    raw = getattr(settings, "ADS_S2S_MODE", "on")
    if not isinstance(raw, str):
        raw = str(raw)
    mode = raw.strip().lower() or "on"
    if mode not in _VALID_MODES:
        return "on"
    return mode  # type: ignore[return-value]


def tracking_enabled() -> bool:
    return current_mode() != "off"


def capture_enabled() -> bool:
    return current_mode() == "capture"


def upload_enabled() -> bool:
    return current_mode() == "on"


def mock_enabled() -> bool:
    return current_mode() == "mock"


def should_enqueue() -> bool:
    return current_mode() in {"on", "mock"}


def hold_reason() -> str:
    return "Capture mode active" if capture_enabled() else ""


@dataclass(frozen=True)
class ModeState:
    mode: AdsMode
    tracking: bool
    capture: bool
    upload: bool
    mock: bool


def describe_mode() -> ModeState:
    mode = current_mode()
    return ModeState(
        mode=mode,
        tracking=mode != "off",
        capture=mode == "capture",
        upload=mode == "on",
        mock=mode == "mock",
    )


def mode_message() -> str:
    mode = current_mode()
    if mode == "off":
        return "Mode off: conversions not captured."
    if mode == "capture":
        return "Mode capture: conversions held without uploads."
    if mode == "mock":
        return "Mode mock: uploads simulated without calling Google Ads."
    return "Mode on: uploads active."
