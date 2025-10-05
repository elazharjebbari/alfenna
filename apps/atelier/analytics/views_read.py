"""Read-only analytics endpoints for aggregated metrics."""
from __future__ import annotations

from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ComponentStatDaily, HeatmapBucketDaily


class ComponentStatsView(APIView):
    """Return daily component aggregates filtered by page/slot."""

    def get(self, request, *args, **kwargs) -> Response:
        date_param = request.query_params.get("date")
        target_date = parse_date(date_param) if date_param else timezone.now().date()
        if target_date is None:
            return Response({"detail": "Invalid date."}, status=status.HTTP_400_BAD_REQUEST)

        page_id = request.query_params.get("page_id")
        if not page_id:
            return Response({"detail": "page_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        site_version = request.query_params.get("site_version", "")
        slot_id = request.query_params.get("slot_id")
        component_alias = request.query_params.get("component_alias")

        qs = ComponentStatDaily.objects.filter(date=target_date, page_id=page_id)
        if site_version:
            qs = qs.filter(site_version=site_version)
        if slot_id:
            qs = qs.filter(slot_id=slot_id)
        if component_alias:
            qs = qs.filter(component_alias=component_alias)

        results = [
            {
                "page_id": obj.page_id,
                "slot_id": obj.slot_id,
                "component_alias": obj.component_alias,
                "site_version": obj.site_version,
                "impressions": obj.impressions,
                "clicks": obj.clicks,
                "avg_scroll_pct": obj.avg_scroll_pct,
                "uu_count": obj.uu_count,
                "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
            }
            for obj in qs.order_by("slot_id", "component_alias")
        ]

        return Response({
            "date": target_date.isoformat(),
            "page_id": page_id,
            "site_version": site_version,
            "results": results,
        })


class HeatmapBucketsView(APIView):
    """Return aggregated heatmap buckets for a given page/date."""

    def get(self, request, *args, **kwargs) -> Response:
        date_param = request.query_params.get("date")
        target_date = parse_date(date_param) if date_param else timezone.now().date()
        if target_date is None:
            return Response({"detail": "Invalid date."}, status=status.HTTP_400_BAD_REQUEST)

        page_id = request.query_params.get("page_id")
        if not page_id:
            return Response({"detail": "page_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        site_version = request.query_params.get("site_version", "")
        device = request.query_params.get("device")

        qs = HeatmapBucketDaily.objects.filter(date=target_date, page_id=page_id)
        if site_version:
            qs = qs.filter(site_version=site_version)
        if device:
            qs = qs.filter(device=device)

        buckets = [
            {
                "device": obj.device,
                "bucket_x": obj.bucket_x,
                "bucket_y": obj.bucket_y,
                "hits": obj.hits,
            }
            for obj in qs.order_by("device", "bucket_x", "bucket_y")
        ]

        return Response({
            "date": target_date.isoformat(),
            "page_id": page_id,
            "site_version": site_version,
            "buckets": buckets,
        })


__all__ = ["ComponentStatsView", "HeatmapBucketsView"]
