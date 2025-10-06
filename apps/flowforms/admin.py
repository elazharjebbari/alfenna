from django.contrib import admin
from .models import FlowSession, FlowStatus

@admin.register(FlowSession)
class FlowSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "flow_key", "session_key", "lead", "current_step", "status", "last_touch_at", "reminder_count")
    list_filter = ("flow_key", "status")
    search_fields = ("session_key", "lead__email", "lead__phone", "lead__id", "flow_key", "current_step")
    readonly_fields = ("created_at", "updated_at", "last_touch_at")