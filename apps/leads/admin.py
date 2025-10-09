from django.contrib import admin
from .models import Lead, LeadEvent, LeadSubmissionLog


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "form_kind",
        "email",
        "phone",
        "pack_slug",
        "payment_mode",
        "status",
        "score",
        "campaign",
        "created_at",
    )
    list_filter = ("form_kind", "status", "campaign", "country", "billing_country")
    search_fields = (
        "email",
        "phone",
        "course_slug",
        "pack_slug",
        "company_name",
        "idempotency_key",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "signed_token_hash",
        "ip_addr",
        "user_agent",
        "referer",
        "page_path",
        "context_complementaries",
        "context_quantity",
        "context_promotion",
    )

    fieldsets = (
        (
            "Identification",
            {
                "fields": (
                    "form_kind",
                    "status",
                    "score",
                    "campaign",
                    "source",
                    "utm_source",
                    "utm_medium",
                    "utm_campaign",
                )
            },
        ),
        (
            "Contact",
            {
                "fields": (
                    "email",
                    "phone",
                    "full_name",
                    "first_name",
                    "last_name",
                )
            },
        ),
        (
            "Adresse",
            {
                "fields": (
                    "address_line1",
                    "address_line2",
                    "city",
                    "state",
                    "postal_code",
                    "country",
                )
            },
        ),
        (
            "Commande",
            {
                "fields": (
                    "pack_slug",
                    "course_slug",
                    "payment_mode",
                    "currency",
                    "context_quantity",
                    "context_promotion",
                )
            },
        ),
        (
            "Contexte",
            {"fields": ("context_complementaries",)},
        ),
        (
            "Tech",
            {
                "classes": ("collapse",),
                "fields": (
                    "idempotency_key",
                    "signed_token_hash",
                    "ip_addr",
                    "user_agent",
                    "referer",
                    "page_path",
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

    def context_complementaries(self, obj: Lead) -> str:
        ctx = obj.context or {}
        complementary = ctx.get("complementary_slugs") or []
        return ", ".join(complementary) if complementary else "—"

    context_complementaries.short_description = "Produits complémentaires"

    def context_quantity(self, obj: Lead) -> str:
        ctx = obj.context or {}
        value = ctx.get("quantity") or ctx.get("quantity_requested")
        return str(value) if value not in (None, "") else "—"

    context_quantity.short_description = "Quantité (stepper)"

    def context_promotion(self, obj: Lead) -> str:
        ctx = obj.context or {}
        value = ctx.get("promotion_selected") or ctx.get("promotion")
        return str(value) if value else "—"

    context_promotion.short_description = "Promotion"

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
