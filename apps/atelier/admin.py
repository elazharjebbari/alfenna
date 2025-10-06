"""Admin registrations for Atelier analytics."""
from django.contrib import admin

from .analytics.models import AnalyticsEventRaw, ComponentStatDaily, HeatmapBucketDaily


@admin.register(ComponentStatDaily)
class ComponentStatDailyAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "site_version",
        "page_id",
        "slot_id",
        "component_alias",
        "impressions",
        "clicks",
        "avg_scroll_pct",
        "uu_count",
    )
    list_filter = ("date", "site_version", "page_id")
    search_fields = ("page_id", "slot_id", "component_alias")
    ordering = ("-date", "page_id", "slot_id")


@admin.register(HeatmapBucketDaily)
class HeatmapBucketDailyAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "site_version",
        "page_id",
        "device",
        "bucket_x",
        "bucket_y",
        "hits",
    )
    list_filter = ("date", "site_version", "page_id", "device")
    ordering = ("-date", "page_id", "device", "bucket_x", "bucket_y")


@admin.register(AnalyticsEventRaw)
class AnalyticsEventRawAdmin(admin.ModelAdmin):
    list_display = ("ts", "event_type", "page_id", "slot_id", "component_alias", "request_id")
    list_filter = ("event_type", "site_version", "device")
    search_fields = ("event_uuid", "page_id", "slot_id", "component_alias", "request_id")
    readonly_fields = ("payload",)
    ordering = ("-ts",)
