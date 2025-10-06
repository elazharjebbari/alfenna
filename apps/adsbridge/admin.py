"""Admin configuration for the ads bridge app."""

from __future__ import annotations

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils import timezone

from . import conf as ads_conf, models, tasks


@admin.register(models.ConversionRecord)
class ConversionRecordAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "kind",
        "action_key",
        "status",
        "effective_mode",
        "order_id",
        "lead_id",
        "event_at",
        "attempt_count",
        "created_at",
    )
    list_filter = ("status", "kind", "effective_mode", "created_at")
    search_fields = ("order_id", "lead_id", "gclid", "gbraid", "wbraid", "idempotency_key")
    readonly_fields = (
        "created_at",
        "updated_at",
        "idempotency_key",
        "attempt_count",
        "action_key",
        "enhanced_identifiers",
        "google_upload_status",
        "hold_reason",
        "effective_mode",
    )
    actions = ["retry_records", "release_held_records"]

    @admin.action(description="Re-enqueue selected conversions")
    def retry_records(self, request: HttpRequest, queryset: QuerySet[models.ConversionRecord]) -> None:
        ids = list(queryset.values_list("id", flat=True))
        mode = ads_conf.current_mode()
        if not ads_conf.should_enqueue():
            messages.warning(
                request,
                "Uploads are not active in mode '%s'. Records will remain held." % mode,
            )
        for record_id in ids:
            tasks.enqueue_conversion(record_id)
        self.message_user(request, f"Re-enqueued {len(ids)} conversion record(s)")

    @admin.action(description="Release held conversions (HELD → PENDING)")
    def release_held_records(self, request: HttpRequest, queryset: QuerySet[models.ConversionRecord]) -> None:
        mode = ads_conf.current_mode()
        if mode not in {"on", "mock"}:
            messages.warning(
                request,
                "Cannot release held records while ADS_S2S_MODE is '%s'." % mode,
            )
            return

        held_queryset = queryset.filter(status=models.ConversionRecord.Status.HELD)
        count = 0
        for record in held_queryset:
            record.status = models.ConversionRecord.Status.PENDING
            record.hold_reason = ""
            record.effective_mode = mode
            record.updated_at = timezone.now()
            record.save(update_fields=["status", "hold_reason", "effective_mode", "updated_at"])
            tasks.enqueue_conversion(record.id)
            count += 1

        self.message_user(request, f"Released {count} held conversion record(s)")
