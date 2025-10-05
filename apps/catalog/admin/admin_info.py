from django.contrib import admin
from ..models import (
    CourseTrainingContent, TrainingDescriptionBlock, TrainingBundleItem,
    TrainingCurriculumSection, TrainingCurriculumItem, TrainingInstructor, TrainingReview,
    CourseSidebarSettings, SidebarInfoItem, SidebarBundleItem, SidebarLink
)

# --- Training ---
class TrainingDescriptionInline(admin.TabularInline):
    model = TrainingDescriptionBlock
    extra = 0

class TrainingBundleInline(admin.TabularInline):
    model = TrainingBundleItem
    extra = 0

class TrainingInstructorInline(admin.TabularInline):
    model = TrainingInstructor
    extra = 0

class TrainingReviewInline(admin.TabularInline):
    model = TrainingReview
    extra = 0

@admin.register(CourseTrainingContent)
class CourseTrainingContentAdmin(admin.ModelAdmin):
    list_display = ("course", "title", "updated_at")
    search_fields = ("course__title", "title")
    inlines = [TrainingDescriptionInline, TrainingBundleInline, TrainingInstructorInline, TrainingReviewInline]

@admin.register(TrainingCurriculumSection)
class TrainingCurriculumSectionAdmin(admin.ModelAdmin):
    list_display = ("training", "order", "title")
    list_filter = ("training__course",)
    search_fields = ("title",)

@admin.register(TrainingCurriculumItem)
class TrainingCurriculumItemAdmin(admin.ModelAdmin):
    list_display = ("section", "order", "text")
    list_filter = ("section__training__course",)
    search_fields = ("text",)

# --- Sidebar ---
class SidebarInfoInline(admin.TabularInline):
    model = SidebarInfoItem
    extra = 0

class SidebarBundleInline(admin.TabularInline):
    model = SidebarBundleItem
    extra = 0

class SidebarLinkInline(admin.TabularInline):
    model = SidebarLink
    extra = 0
    max_num = 2

@admin.register(CourseSidebarSettings)
class CourseSidebarSettingsAdmin(admin.ModelAdmin):
    list_display = ("course", "currency", "promo_badge", "updated_at")
    search_fields = ("course__title",)
    inlines = [SidebarInfoInline, SidebarBundleInline, SidebarLinkInline]