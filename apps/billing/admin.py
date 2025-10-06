from __future__ import annotations

from django.contrib import admin, messages

from apps.billing.services import get_invoice_service
from apps.billing.tasks import send_invoice_email

from .models import (
    CustomerProfile,
    Entitlement,
    InvoiceArtifact,
    Order,
    OrderItem,
    Payment,
    PaymentAttempt,
    PaymentLog,
    Refund,
    WebhookEvent,
)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product_sku", "quantity", "unit_amount", "description")


class PaymentAttemptInline(admin.TabularInline):
    model = PaymentAttempt
    extra = 0
    readonly_fields = ("intent_id", "status", "idempotency_key", "created_at")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "reference",
        "user",
        "email",
        "price_plan",
        "course",
        "amount_total",
        "currency",
        "status",
        "stripe_payment_intent_id",
        "created_at",
    )
    list_filter = ("status", "currency", "price_plan", "course")
    search_fields = ("id", "reference", "email", "stripe_payment_intent_id", "pricing_code")
    date_hierarchy = "created_at"
    inlines = [OrderItemInline, PaymentAttemptInline]
    actions = ["regenerate_invoice_pdf", "resend_invoice_email"]

    @admin.action(description="Regénérer la facture PDF")
    def regenerate_invoice_pdf(self, request, queryset):
        service = get_invoice_service()
        regenerated = 0
        for order in queryset:
            try:
                service.generate(order)
            except Exception as exc:  # pragma: no cover - admin only
                self.message_user(
                    request,
                    f"Erreur lors de la régénération pour la commande {order.id}: {exc}",
                    level=messages.ERROR,
                )
            else:
                regenerated += 1
        if regenerated:
            self.message_user(request, f"{regenerated} facture(s) régénérée(s).", level=messages.SUCCESS)

    @admin.action(description="Renvoyer l'e-mail de facture")
    def resend_invoice_email(self, request, queryset):
        enqueued = 0
        for order in queryset:
            send_invoice_email.delay(order.id)
            enqueued += 1
        if enqueued:
            self.message_user(
                request,
                f"{enqueued} e-mail(s) de facture reprogrammés.",
                level=messages.SUCCESS,
            )


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "email", "stripe_customer_id", "guest_id", "created_at")
    search_fields = ("email", "stripe_customer_id", "guest_id")
    list_filter = ("created_at",)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "stripe_payment_intent_id",
        "status",
        "amount_received",
        "currency",
        "created_at",
    )
    search_fields = ("stripe_payment_intent_id", "order__id")


@admin.register(PaymentAttempt)
class PaymentAttemptAdmin(admin.ModelAdmin):
    list_display = ("order", "intent_id", "status", "created_at")
    search_fields = ("intent_id", "order__id", "idempotency_key")
    list_filter = ("status",)


@admin.register(PaymentLog)
class PaymentLogAdmin(admin.ModelAdmin):
    list_display = ("order", "event_type", "created_at")
    search_fields = ("order__id", "event_type")
    date_hierarchy = "created_at"


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ("order", "refund_id", "amount", "status", "created_at")
    search_fields = ("refund_id", "order__id")
    list_filter = ("status",)


@admin.register(InvoiceArtifact)
class InvoiceArtifactAdmin(admin.ModelAdmin):
    list_display = ("order", "kind", "storage_path", "rendered_at")
    search_fields = ("order__id", "storage_path")
    list_filter = ("kind",)


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "event_type", "status", "processed_at", "order")
    search_fields = ("event_id", "event_type", "order__id")
    list_filter = ("status", "event_type")
    date_hierarchy = "processed_at"


@admin.register(Entitlement)
class EntitlementAdmin(admin.ModelAdmin):
    list_display = ("user", "course", "granted_at")
    search_fields = ("user__username", "course__slug", "user__email")
    list_filter = ("course",)
