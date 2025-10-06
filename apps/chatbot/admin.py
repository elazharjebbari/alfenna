"""Admin registrations for the chatbot app."""

from django.contrib import admin

from .models import ChatMessage, ChatSession, ConsentEvent, ProviderCall


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = (
        "session_key",
        "consent_snapshot",
        "locale",
        "user",
        "created_at",
        "last_activity",
        "closed_at",
    )
    search_fields = ("session_key", "user__email", "user__username")
    list_filter = ("locale", "closed_at")
    readonly_fields = ("id", "created_at", "updated_at", "last_activity")


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("session", "role", "short_content", "created_at")
    search_fields = ("session__session_key", "content")
    list_filter = ("role",)
    readonly_fields = ("created_at", "updated_at")

    @staticmethod
    def short_content(obj: ChatMessage) -> str:  # type: ignore[name-defined]
        return obj.content[:80]


@admin.register(ConsentEvent)
class ConsentEventAdmin(admin.ModelAdmin):
    list_display = ("session", "user", "value", "ip", "created_at")
    list_filter = ("value",)
    search_fields = ("ip", "user_agent", "session__session_key", "user__email")
    readonly_fields = ("created_at",)


@admin.register(ProviderCall)
class ProviderCallAdmin(admin.ModelAdmin):
    list_display = ("session", "provider", "model", "status", "duration_ms", "created_at")
    list_filter = ("provider", "status")
    search_fields = ("session__session_key", "provider", "model")
    readonly_fields = ("created_at", "updated_at")
