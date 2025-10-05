"""API endpoints for analytics ingestion."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List
import logging

from django.conf import settings
from django.http import HttpRequest
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import CollectBatchSerializer
from .throttling import AnalyticsIPThrottle
from . import tasks


log = logging.getLogger("atelier.analytics.collect")


def _get_segments(request: HttpRequest) -> Any:
    return getattr(request, "_segments", None)


class CollectAPIView(APIView):
    throttle_classes = [AnalyticsIPThrottle]

    def post(self, request: HttpRequest, *args, **kwargs) -> Response:
        if not getattr(settings, "ANALYTICS_ENABLED", True):
            return Response(status=status.HTTP_204_NO_CONTENT)

        segments = _get_segments(request)
        consent = getattr(segments, "consent", "N")
        if consent != "Y":
            return Response(status=status.HTTP_204_NO_CONTENT)

        if settings.DEBUG:
            raw_events = []
            try:
                raw_events = request.data.get("events", [])  # type: ignore[attr-defined]
            except Exception:
                raw_events = []
            if isinstance(raw_events, list):
                invalid = [item for item in raw_events if not isinstance(item, dict) or not (item.get("event_type") or item.get("event"))]
                if invalid:
                    sample = invalid[0] if invalid else None
                    log.warning("ANALYTICS DEBUG: %d invalid event(s) received; sample=%r", len(invalid), sample)

        serializer = CollectBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        events: List[Dict[str, Any]] = serializer.validated_data.get("events", [])
        if not events:
            return Response(status=status.HTTP_204_NO_CONTENT)

        # Shared context captured once to minimise payload size.
        ctx = {
            "request_id": getattr(request, "request_id", ""),
            "site_version": getattr(request, "site_version", "core"),
            "lang": getattr(segments, "lang", ""),
            "device": getattr(segments, "device", ""),
            "path": request.get_full_path(),
            "referer": (request.META.get("HTTP_REFERER") or "")[:512],
            "user_id": self._resolve_user_id(request),
            "consent": consent,
            "user_agent": (request.META.get("HTTP_USER_AGENT") or "")[:512],
            "ip": (request.META.get("REMOTE_ADDR") or "")[:128],
            "host": request.get_host() if hasattr(request, "get_host") else "",
        }

        # Flatten events to include context but leave heavy work to Celery.
        enriched: List[Dict[str, Any]] = []
        for event in events:
            entry = dict(event)
            ts = entry.get("ts")
            if isinstance(ts, datetime):
                entry["ts"] = ts.isoformat()
            entry.setdefault("request_id", ctx["request_id"])
            entry.setdefault("site_version", ctx["site_version"])
            entry.setdefault("lang", ctx["lang"])
            entry.setdefault("device", ctx["device"])
            entry.setdefault("user_id", ctx["user_id"])
            entry.setdefault("consent", ctx["consent"])
            if not entry.get("path"):
                entry["path"] = ctx["path"]
            if not entry.get("referer"):
                entry["referer"] = ctx["referer"]
            enriched.append(entry)

        tasks.persist_raw.delay(enriched, meta={
            "user_agent": ctx["user_agent"],
            "ip": ctx["ip"],
            "host": ctx["host"],
        })
        return Response({"accepted": len(enriched)}, status=status.HTTP_202_ACCEPTED)

    @staticmethod
    def _resolve_user_id(request: HttpRequest) -> str:
        user = getattr(request, "user", None)
        if getattr(user, "is_authenticated", False):
            return str(getattr(user, "pk", ""))
        return ""


__all__ = ["CollectAPIView"]
