"""Analytics storage for raw events and daily aggregates."""
from __future__ import annotations

from django.db import models
from django.utils import timezone


class AnalyticsEventRaw(models.Model):
    """Raw event storage for component analytics."""

    EVENT_TYPES = (
        ("view", "View"),
        ("click", "Click"),
        ("scroll", "Scroll depth"),
        ("heatmap", "Heatmap click"),
    )

    id = models.BigAutoField(primary_key=True)
    event_uuid = models.UUIDField(unique=True)
    ts = models.DateTimeField(default=timezone.now, db_index=True)
    request_id = models.CharField(max_length=64, blank=True, db_index=True)
    site_version = models.CharField(max_length=32, blank=True, db_index=True)
    page_id = models.CharField(max_length=128, blank=True, db_index=True)
    slot_id = models.CharField(max_length=128, blank=True, db_index=True)
    component_alias = models.CharField(max_length=128, blank=True, db_index=True)
    event_type = models.CharField(max_length=16, choices=EVENT_TYPES)
    user_id = models.CharField(max_length=64, blank=True)
    consent = models.CharField(max_length=1)
    lang = models.CharField(max_length=8, blank=True)
    device = models.CharField(max_length=8, blank=True, db_index=True)
    path = models.CharField(max_length=512, blank=True)
    referer = models.CharField(max_length=512, blank=True)
    ua_hash = models.CharField(max_length=64, blank=True, db_index=True)
    ip_hash = models.CharField(max_length=64, blank=True, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "atelier"
        db_table = "atelier_analytics_event_raw"
        indexes = [
            models.Index(fields=["page_id", "slot_id", "event_type", "ts"], name="aa_raw_page_slot_evt"),
            models.Index(fields=["component_alias", "event_type", "ts"], name="aa_raw_alias_evt"),
        ]
        verbose_name = "Analytics Raw Event"
        verbose_name_plural = "Analytics Raw Events"

    def __str__(self) -> str:  # pragma: no cover - debug only
        return f"{self.event_type}:{self.component_alias or '-'}@{self.ts.isoformat()}"


class ComponentStatDaily(models.Model):
    """Daily aggregates for component level metrics."""

    date = models.DateField()
    site_version = models.CharField(max_length=32, blank=True)
    page_id = models.CharField(max_length=128, blank=True)
    slot_id = models.CharField(max_length=128, blank=True)
    component_alias = models.CharField(max_length=128, blank=True)
    impressions = models.PositiveIntegerField(default=0)
    clicks = models.PositiveIntegerField(default=0)
    avg_scroll_pct = models.FloatField(default=0.0)
    uu_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "atelier"
        db_table = "atelier_component_stat_daily"
        unique_together = (
            "date",
            "site_version",
            "page_id",
            "slot_id",
            "component_alias",
        )
        indexes = [
            models.Index(fields=["date", "page_id", "slot_id"], name="aa_cmp_daily_lookup"),
        ]
        verbose_name = "Component Daily Stat"
        verbose_name_plural = "Component Daily Stats"

    def __str__(self) -> str:  # pragma: no cover - debug only
        return f"{self.date}:{self.component_alias or '-'}"


class HeatmapBucketDaily(models.Model):
    """Daily aggregated heatmap buckets (0-99 grid)."""

    date = models.DateField()
    site_version = models.CharField(max_length=32, blank=True)
    page_id = models.CharField(max_length=128, blank=True)
    device = models.CharField(max_length=8, blank=True)
    bucket_x = models.PositiveSmallIntegerField()
    bucket_y = models.PositiveSmallIntegerField()
    hits = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "atelier"
        db_table = "atelier_heatmap_bucket_daily"
        unique_together = (
            "date",
            "site_version",
            "page_id",
            "device",
            "bucket_x",
            "bucket_y",
        )
        indexes = [
            models.Index(fields=["date", "page_id", "device"], name="aa_heatmap_lookup"),
        ]
        verbose_name = "Heatmap Bucket Daily"
        verbose_name_plural = "Heatmap Bucket Daily"

    def __str__(self) -> str:  # pragma: no cover - debug only
        return f"{self.date}:{self.page_id}:{self.bucket_x}x{self.bucket_y}"


__all__ = [
    "AnalyticsEventRaw",
    "ComponentStatDaily",
    "HeatmapBucketDaily",
]
