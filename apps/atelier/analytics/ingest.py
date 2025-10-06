"""Compatibility helpers around analytics ingestion."""
from __future__ import annotations

from typing import Dict, List

from rest_framework.exceptions import ValidationError

from .serializers import CollectBatchSerializer


def validate_batch(payload: Dict) -> List[Dict]:
    """Validate a raw ingestion payload and return normalized events."""
    serializer = CollectBatchSerializer(data=payload)
    if not serializer.is_valid():
        raise ValidationError(serializer.errors)
    return serializer.validated_data.get("events", [])


def persist_events(events: List[Dict], request_id: str | None, consent: str | None) -> None:
    """Placeholder for compatibility, real ingestion handled in tasks.persist_raw."""
    from . import tasks

    if consent != "Y" or not events:
        return
    tasks.persist_raw.delay(events, meta={"request_id": request_id or ""})
