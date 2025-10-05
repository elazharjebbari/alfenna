from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from apps.atelier.compose import pipeline, response
from apps.marketing.mixins import SeoViewMixin
from apps.pages.mixins import CourseSlugGuardMixin


class LearnCourseView(LoginRequiredMixin, CourseSlugGuardMixin, SeoViewMixin, TemplateView):
    """Render the standard lecture screen through the Compose pipeline."""

    template_name = "screens/lecture.html"

    def get(self, request, *args, **kwargs):
        course = self.get_course()
        request._demo_only = False

        route_kwargs = {"course_slug": course.slug}
        lecture_slug = kwargs.get("lecture_slug")
        if lecture_slug:
            route_kwargs["lecture_slug"] = lecture_slug

        request._route_kwargs = route_kwargs
        resolver_match = getattr(request, "resolver_match", None)
        if resolver_match and isinstance(getattr(resolver_match, "kwargs", None), dict):
            resolver_match.kwargs.update(route_kwargs)

        page_ctx = pipeline.build_page_spec("lecture", request, extra=route_kwargs)

        fragments = {}
        for slot_id, slot_ctx in (page_ctx.get("slots") or {}).items():
            rendered = pipeline.render_slot_fragment(page_ctx, slot_ctx, request)
            fragments[slot_id] = rendered.get("html", "")

        assets = pipeline.collect_page_assets(page_ctx)

        return response.render_base(page_ctx, fragments, assets, request)
