from django.contrib import admin

from apps.marketing.models.models_base import MarketingGlobal
from apps.marketing.models.models_pricing import PricePlan, PriceFeature, PriceBonusItem


@admin.register(MarketingGlobal)
class MarketingGlobalAdmin(admin.ModelAdmin):
    list_display = ("site_name", "base_url", "default_locale", "updated_at")
    fieldsets = (
        ("General", {"fields": ("site_name", "base_url", "default_locale", "default_image")}),
        ("Reseaux sociaux", {"fields": ("twitter_site", "twitter_creator", "facebook_app_id")}),
        ("Tracking", {"fields": ("gtm_id", "ga4_id", "meta_pixel_id", "tiktok_pixel_id", "consent_cookie_name")}),
        ("Robots", {"fields": ("robots_default",)}),
    )


class PriceFeatureInline(admin.TabularInline):
    model = PriceFeature
    extra = 0


class PriceBonusItemInline(admin.TabularInline):
    model = PriceBonusItem
    extra = 0


@admin.register(PricePlan)
class PricePlanAdmin(admin.ModelAdmin):
    list_display = ("slug", "title", "price_cents", "currency", "is_active", "priority")
    list_filter = ("is_active", "currency")
    search_fields = ("slug", "title")
    ordering = ("priority", "display_order", "id")
    inlines = (PriceFeatureInline, PriceBonusItemInline)
    fieldsets = (
        ("Identite", {"fields": ("slug", "title", "priority", "display_order", "is_active", "is_featured", "ribbon_label")}),
        ("Tarification", {"fields": ("price_cents", "old_price_cents", "currency", "currency_symbol", "payment_note")}),
        ("Contenu", {"fields": ("features", "value_breakdown")}),
        ("CTA primaire", {"fields": ("cta_label", "cta_url", "cta_sublabel", "cta_aria")}),
        ("CTA secondaire", {"fields": ("second_cta_label", "second_cta_url", "second_cta_aria")}),
    )


@admin.register(PriceFeature)
class PriceFeatureAdmin(admin.ModelAdmin):
    list_display = ("plan", "label", "included", "sort_order")
    list_filter = ("included", "plan__slug")
    search_fields = ("label", "plan__slug")
    ordering = ("plan__priority", "sort_order", "id")


@admin.register(PriceBonusItem)
class PriceBonusItemAdmin(admin.ModelAdmin):
    list_display = ("plan", "label", "amount_cents", "sort_order")
    search_fields = ("label", "plan__slug")
    ordering = ("plan__priority", "sort_order", "id")
