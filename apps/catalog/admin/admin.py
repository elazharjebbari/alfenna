from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone

from apps.catalog.models import Gallery, GalleryItem
from apps.catalog.models.models import Course, CoursePrice
from apps.content.models import Section

class SectionInline(admin.TabularInline):
    model = Section
    extra = 0
    fields = ('order', 'title', 'is_published')
    ordering = ('order',)
    show_change_link = True

class CoursePriceInline(admin.TabularInline):
    model = CoursePrice
    extra = 1
    fields = ("currency", "country", "amount_cents", "active", "effective_at", "expires_at")
    ordering = ("currency", "country", "-effective_at")


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "slug", "is_published", "updated_at")
    inlines = [CoursePriceInline]
    list_filter = ('is_published',)
    search_fields = ('title', 'slug', 'seo_title', 'seo_description')
    readonly_fields = ('course_key', 'published_at', 'plan_version', 'created_at', 'updated_at', 'preview_link')
    prepopulated_fields = { 'slug': ('title',) }
    fieldsets = (
        ('Contenu', {'fields': ('title', 'slug', 'description', 'image')}),
        ('SEO', {'fields': ('seo_title', 'seo_description')}),
        ('Publication', {'fields': ('is_published', 'published_at')}),
        ('Tech', {'fields': ('course_key', 'plan_version', 'created_at', 'updated_at', 'preview_link')}),
    )

    def preview_link(self, obj):
        if not obj.pk:
            return "—"
        return format_html('<a target="_blank" href="{}?preview=1">Prévisualiser</a>', obj.get_absolute_url())

    @admin.action(description="Publier les cours sélectionnés")
    def publish(self, request, queryset):
        queryset.update(is_published=True, published_at=timezone.now())

    @admin.action(description="Dépublier les cours sélectionnés")
    def unpublish(self, request, queryset):
        queryset.update(is_published=False)

    actions = ['publish', 'unpublish']

@admin.register(Gallery)
class GalleryAdmin(admin.ModelAdmin):
    list_display = ("slug", "title", "namespace", "is_active", "updated_at")
    list_filter = ("is_active", "namespace")
    search_fields = ("slug", "title", "subtitle", "product_code")
    readonly_fields = ("created_at", "updated_at")

class GalleryItemInline(admin.TabularInline):
    model = GalleryItem
    fields = ("sort_order","name","badge","meta","image","webp","href","alt","caption","product_code","is_published")
    extra = 0

@admin.register(GalleryItem)
class GalleryItemAdmin(admin.ModelAdmin):
    list_display = ("name", "gallery", "badge", "is_published", "sort_order", "updated_at")
    list_filter = ("gallery", "is_published", "badge", "lang_code")
    search_fields = ("name", "meta", "caption", "image", "product_code")
    ordering = ("gallery", "sort_order", "id")
    readonly_fields = ("created_at", "updated_at")