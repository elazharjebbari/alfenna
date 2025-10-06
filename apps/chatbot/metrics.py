"""Lightweight metrics helpers for the chatbot domain."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping

from django.core.cache import cache
from django.utils import timezone

log = logging.getLogger("chatbot.metrics")

_METRIC_KEY_PREFIX = "chatbot:metrics:"


def _cache_key(name: str) -> str:
    return f"{_METRIC_KEY_PREFIX}{name}"


def increment(name: str, amount: int = 1, **context: Any) -> None:
    key = _cache_key(name)
    try:
        cache.incr(key, amount)
    except ValueError:
        cache.set(key, amount, None)
    log.debug("metric_increment", extra={"metric": name, "amount": amount, **context})


def gauge(name: str, value: float, **context: Any) -> None:
    cache.set(_cache_key(name), value, None)
    log.debug("metric_gauge", extra={"metric": name, "value": value, **context})


def snapshot() -> Mapping[str, Any]:
    keys = [
        "sessions_total",
        "turns_total",
        "turns_error",
        "latency_p95",
    ]
    data = {key: cache.get(_cache_key(key), 0) for key in keys}
    data["timestamp"] = timezone.now().isoformat()
    return data


def record_session_started(session_id: str, *, locale: str) -> None:
    increment("sessions_total", locale=locale)
    log.info(
        "session_started",
        extra={"session_id": session_id, "locale": locale},
    )


def record_turn_completed(
    *,
    session_id: str,
    provider: str,
    duration_ms: int,
    error: str | None,
) -> None:
    increment("turns_total", provider=provider)
    if error:
        increment("turns_error", provider=provider)
    gauge("latency_p95", float(duration_ms))
    log.info(
        "turn_completed",
        extra={
            "session_id": session_id,
            "provider": provider,
            "duration_ms": duration_ms,
            "error": error or "",
        },
    )
