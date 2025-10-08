from django.contrib import admin
from .models import Lead, LeadEvent, LeadSubmissionLog


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("id", "form_kind", "email", "phone", "status", "score", "campaign", "created_at")
    list_filter = ("form_kind", "status", "campaign", "country", "billing_country")
    search_fields = ("email", "phone", "course_slug", "company_name", "idempotency_key")
    readonly_fields = ("created_at", "updated_at", "signed_token_hash", "ip_addr", "user_agent", "referer", "page_path")

@admin.register(LeadEvent)
class LeadEventAdmin(admin.ModelAdmin):
    list_display = ("lead", "event", "created_at")
    search_fields = ("lead__id", "event")
    date_hierarchy = "created_at"

@admin.register(LeadSubmissionLog)
class LeadSubmissionLogAdmin(admin.ModelAdmin):
    list_display = ("lead", "flow_key", "session_key", "step", "status", "attempt_count", "created_at")
    list_filter = ("flow_key", "status", "step")
    search_fields = ("lead__id", "flow_key", "session_key", "step", "message")
    date_hierarchy = "created_at"
    readonly_fields = ("created_at", "updated_at", "payload", "last_error")
