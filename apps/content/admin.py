from django.contrib import admin
from parler.admin import TranslatableAdmin, TranslatableTabularInline

from .models import Section, Lecture


class LectureInline(TranslatableTabularInline):
    model = Lecture
    extra = 0
    fields = ('order', 'title', 'type', 'is_published', 'is_free')
    ordering = ('order',)


@admin.register(Section)
class SectionAdmin(TranslatableAdmin):
    list_display = ('course', 'order', 'title', 'is_published')
    list_filter = ('course', 'is_published')
    search_fields = ('title', 'course__title')
    ordering = ('course', 'order')
    inlines = [LectureInline]


@admin.register(Lecture)
class LectureAdmin(TranslatableAdmin):
    list_display = ('section', 'order', 'title', 'type', 'is_published', 'is_free')
    list_filter = ('type', 'is_published', 'is_free', 'section__course')
    search_fields = ('title', 'section__title', 'section__course__title')
    ordering = ('section', 'order')
