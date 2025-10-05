"""Instrumentation helpers for messaging flows (password reset, etc.)."""
from __future__ import annotations

from typing import Any

try:  # pragma: no cover - optional dependency
    from prometheus_client import Counter  # type: ignore
except Exception:  # pragma: no cover - Prometheus not installed
    Counter = None  # type: ignore


def _build_counter(name: str, documentation: str, labelnames: list[str]) -> Any:
    if Counter is None:  # pragma: no cover - metrics disabled
        return None
    return Counter(name, documentation, labelnames=labelnames)


_RESET_EVENTS_COUNTER = _build_counter(
    "messaging_password_reset_events_total",
    "Password reset email pipeline events.",
    ["event"],
)


def record_password_reset_event(event: str) -> None:
    if _RESET_EVENTS_COUNTER is None:  # pragma: no cover - metrics disabled
        return
    _RESET_EVENTS_COUNTER.labels(event=event).inc()


__all__ = ["record_password_reset_event"]
