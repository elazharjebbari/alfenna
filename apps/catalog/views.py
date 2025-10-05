# apps/catalog/views.py
from django.db.models import Prefetch
from django.views.generic import ListView, DetailView
from apps.catalog.models.models import Course
from apps.content.models import Section, Lecture
from apps.marketing import schema as seo_schema
from apps.marketing.mixins import SeoViewMixin  # <- import absolu clair

class CourseListView(SeoViewMixin, ListView):
    model = Course
    paginate_by = 12
    template_name = 'catalog/course_list.html'

    def get_queryset(self):
        qs = Course.objects.published()
        return qs.select_related().only(
            'id', 'title', 'slug', 'seo_description', 'image', 'published_at', 'updated_at'
        )

    def get_context_data(self, **kwargs):
        # 1) Poser d'abord les méta/JSON-LD
        self.meta_title = "Catalogue des cours"
        self.meta_description = "Découvrez nos formations en ligne."
        self.seo_jsonld = [seo_schema.website_schema(), seo_schema.org_schema()]

        # 2) Laisser le mixin construire `meta` + pousser `seo_jsonld`
        ctx = super().get_context_data(**kwargs)

        # 3) Pagination: le CP marketing lira page_obj depuis request
        self.request.page_obj = ctx.get("page_obj")
        return ctx


class CourseDetailView(SeoViewMixin, DetailView):
    model = Course
    slug_field = 'slug'
    slug_url_kwarg = 'slug'
    template_name = 'catalog/course_detail.html'

    def get_queryset(self):
        preview = bool(self.request.user.is_staff and self.request.GET.get('preview'))
        qs = Course.objects.all() if preview else Course.objects.published()

        section_qs = Section.objects.order_by('order')
        lecture_qs = Lecture.objects.order_by('order')
        if not preview:
            section_qs = section_qs.filter(is_published=True)
            lecture_qs = lecture_qs.filter(is_published=True)

        return qs.prefetch_related(
            Prefetch('sections', queryset=section_qs, to_attr='prefetched_sections'),
            Prefetch('sections__lectures', queryset=lecture_qs, to_attr='prefetched_lectures'),
        )

    def get_context_data(self, **kwargs):
        obj = self.object

        # 1) Poser d'abord les méta/JSON-LD
        self.meta_title = obj.seo_title or obj.title
        self.meta_description = obj.seo_description or (obj.description[:160] if obj.description else "")
        self.meta_type = "product"
        if getattr(obj, "image", None):
            try:
                self.meta_image = obj.image.url
            except Exception:
                self.meta_image = None

        # JSON-LD Course (+ Organization)
        self.seo_jsonld = [seo_schema.course_schema(obj, self.request), seo_schema.org_schema()]

        # 2) Laisser le mixin construire `meta` + pousser `seo_jsonld`
        ctx = super().get_context_data(**kwargs)

        # 3) Contexte existant: garder "preview"
        ctx['preview'] = bool(self.request.user.is_staff and self.request.GET.get('preview'))
        return ctx
