from django.contrib import admin
from .models import Progress, LectureComment

@admin.register(Progress)
class ProgressAdmin(admin.ModelAdmin):
    list_display = ("user", "lecture", "is_completed", "last_position_ms", "last_viewed_at", "completed_at")
    list_filter = ("is_completed", "lecture")
    search_fields = ("user__username", "lecture__title")

@admin.register(LectureComment)
class LectureCommentAdmin(admin.ModelAdmin):
    list_display = ("user", "lecture", "is_visible", "is_flagged", "created_at")
    list_filter = ("is_visible", "is_flagged", "lecture")
    search_fields = ("user__username", "body")
    actions = ["mark_visible", "mark_hidden", "flag", "unflag"]

    def mark_visible(self, request, qs):
        qs.update(is_visible=True)
    def mark_hidden(self, request, qs):
        qs.update(is_visible=False)
    def flag(self, request, qs):
        qs.update(is_flagged=True)
    def unflag(self, request, qs):
        qs.update(is_flagged=False)
