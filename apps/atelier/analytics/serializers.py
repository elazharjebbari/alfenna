"""Serializers for analytics ingestion payloads."""
from __future__ import annotations

from typing import Any, Dict

from django.utils import timezone
from rest_framework import serializers
import json

_VALID_EVENT_TYPES = ("view", "click", "scroll", "heatmap")
_MAX_PAYLOAD_BYTES = 2048
_MAX_EVENTS_PER_BATCH = 50


class EventItemSerializer(serializers.Serializer):
    event_uuid = serializers.UUIDField()
    event_type = serializers.ChoiceField(choices=[(evt, evt) for evt in _VALID_EVENT_TYPES])
    ts = serializers.DateTimeField(required=False)
    page_id = serializers.CharField(max_length=128)
    slot_id = serializers.CharField(max_length=128, allow_blank=True, required=False)
    component_alias = serializers.CharField(max_length=128, allow_blank=True, required=False)
    payload = serializers.DictField(child=serializers.JSONField(), required=False, default=dict)

    def validate_payload(self, value: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(value, dict):
            raise serializers.ValidationError("Payload must be an object.")
        if len(value) > 32:
            raise serializers.ValidationError("Payload has too many keys (max 32).")
        encoded = json.dumps(value, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > _MAX_PAYLOAD_BYTES:
            raise serializers.ValidationError("Payload exceeds maximum size.")
        return value

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        event_type = attrs.get("event_type")
        payload = attrs.get("payload") or {}
        if event_type == "scroll":
            pct = payload.get("scroll_pct")
            if pct is None:
                raise serializers.ValidationError({"payload": "scroll_pct is required for scroll events."})
            try:
                pct_f = float(pct)
            except (TypeError, ValueError):
                raise serializers.ValidationError({"payload": "scroll_pct must be a number."})
            if pct_f < 0 or pct_f > 100:
                raise serializers.ValidationError({"payload": "scroll_pct must be between 0 and 100."})
        if event_type == "heatmap":
            for coord in ("x", "y"):
                val = payload.get(coord)
                if val is None:
                    raise serializers.ValidationError({"payload": f"{coord} is required for heatmap events."})
                try:
                    as_float = float(val)
                except (TypeError, ValueError):
                    raise serializers.ValidationError({"payload": f"{coord} must be a number."})
                if as_float < 0 or as_float > 1:
                    raise serializers.ValidationError({"payload": f"{coord} must be between 0 and 1."})
        if not attrs.get("ts"):
            attrs["ts"] = timezone.now()
        return attrs


class CollectBatchSerializer(serializers.Serializer):
    events = EventItemSerializer(many=True, allow_empty=False)

    def validate_events(self, events):
        if len(events) > _MAX_EVENTS_PER_BATCH:
            raise serializers.ValidationError(f"Too many events (max {_MAX_EVENTS_PER_BATCH}).")
        return events


__all__ = [
    "CollectBatchSerializer",
    "EventItemSerializer",
]
