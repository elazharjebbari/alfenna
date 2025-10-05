from django.shortcuts import get_object_or_404

from apps.catalog.models import Course


class CourseSlugGuardMixin:
    course: Course | None = None

    def get_course(self):
        slug = self.kwargs.get("course_slug", "").strip()
        self.course = get_object_or_404(Course, slug=slug, is_published=True)
        # on le met sur la request pour les hydrators
        setattr(self.request, "_course", self.course)
        return self.course