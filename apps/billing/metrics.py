"""Lightweight helpers for billing observability (metrics, counters)."""

from __future__ import annotations

from typing import Any

from django.conf import settings

try:  # pragma: no cover - optional dependency
    from prometheus_client import Counter  # type: ignore
except Exception:  # pragma: no cover - optional dependency missing
    Counter = None  # type: ignore


def _build_counter(name: str, documentation: str, labelnames: list[str]) -> Any:
    if Counter is None:  # pragma: no cover - no prometheus installed
        return None
    metric_name = f"{settings.BILLING_METRICS_NAMESPACE}_{name}" if hasattr(settings, "BILLING_METRICS_NAMESPACE") else name
    return Counter(metric_name, documentation, labelnames=labelnames)


_WEBHOOK_COUNTER = _build_counter(
    "webhook_processed_total",
    "Total number of Stripe webhook events processed by the billing module.",
    ["event_type", "status"],
)

_INVOICE_DOWNLOAD_COUNTER = _build_counter(
    "invoice_download_total",
    "Number of invoice download attempts.",
    ["status"],
)

_INVOICE_ISSUE_COUNTER = _build_counter(
    "invoice_issue_total",
    "Total number of invoice issuance attempts.",
    ["status"],
)

_INVOICE_EMAIL_COUNTER = _build_counter(
    "invoice_email_enqueue_total",
    "Total number of invoice-related emails enqueued.",
    ["status"],
)


def record_webhook_processed(event_type: str, status: str) -> None:
    if _WEBHOOK_COUNTER is None:  # pragma: no cover - metrics not enabled
        return
    _WEBHOOK_COUNTER.labels(event_type=event_type, status=status).inc()


def record_invoice_download(status: str) -> None:
    if _INVOICE_DOWNLOAD_COUNTER is None:  # pragma: no cover - metrics not enabled
        return
    _INVOICE_DOWNLOAD_COUNTER.labels(status=status).inc()


def record_invoice_issue(status: str) -> None:
    if _INVOICE_ISSUE_COUNTER is None:  # pragma: no cover - metrics not enabled
        return
    _INVOICE_ISSUE_COUNTER.labels(status=status).inc()


def record_invoice_email(status: str) -> None:
    if _INVOICE_EMAIL_COUNTER is None:  # pragma: no cover - metrics not enabled
        return
    _INVOICE_EMAIL_COUNTER.labels(status=status).inc()


__all__ = [
    "record_invoice_download",
    "record_invoice_email",
    "record_invoice_issue",
    "record_webhook_processed",
]
