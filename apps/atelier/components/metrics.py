"""Server-side analytics helpers for component impressions."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Dict
from uuid import uuid4

from django.conf import settings
from django.utils import timezone

from apps.atelier.analytics import tasks

_ALLOWED_CONSENT = {"Y", "y", "yes", "true", "1", "accept"}


def _segments_to_dict(segments: Any) -> Dict[str, Any]:
    if segments is None:
        return {}
    if is_dataclass(segments):
        data = asdict(segments)
    elif isinstance(segments, dict):
        data = dict(segments)
    else:
        data = {}
    return {
        "consent": str(data.get("consent", "N")),
        "lang": str(data.get("lang", "")),
        "device": str(data.get("device", "")),
    }


def record_impression(
    page: str,
    slot: str,
    experiment: str | None,
    variant: str | None,
    request_id: str | None,
    segments: dict | Any,
    qa: bool | None,
    **extra: Any,
) -> None:
    """Enqueue a minimal view event when consent allows it."""
    if not getattr(settings, "ANALYTICS_ENABLED", True):
        return

    seg = _segments_to_dict(segments)
    if seg.get("consent", "N").upper() not in _ALLOWED_CONSENT:
        return

    event = {
        "event_uuid": uuid4().hex,
        "event_type": "view",
        "page_id": page or "",
        "slot_id": slot or "",
        "component_alias": (extra.get("component_alias") or experiment or slot or ""),
        "site_version": extra.get("site_version", ""),
        "lang": seg.get("lang", ""),
        "device": seg.get("device", ""),
        "request_id": request_id or "",
        "consent": "Y",
        "path": extra.get("path", ""),
        "referer": extra.get("referer", ""),
        "payload": {
            "source": "server",
            "qa": bool(qa),
            "variant": variant or "A",
        },
        "ts": timezone.now().isoformat(),
    }

    meta = {
        "user_agent": extra.get("user_agent", ""),
        "ip": extra.get("ip", ""),
        "host": extra.get("host", ""),
    }

    tasks.persist_raw.delay([event], meta=meta)


def should_record(slot_ctx: dict) -> bool:
    if not slot_ctx:
        return False
    if slot_ctx.get("metrics_disabled"):
        return False
    return True


__all__ = ["record_impression", "should_record"]
