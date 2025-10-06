from __future__ import annotations
from typing import Any, Dict, List, Mapping

from django.db.utils import OperationalError, ProgrammingError

from apps.catalog.models.models import Course

PLACEHOLDER_COVER = "https://placehold.co/600x402"


def _clean_str(value: Any, default: str = "") -> str:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned if cleaned else default
    return default


def _clean_int(value: Any, default: int = 0) -> int:
    try:
        integer = int(value)
        return integer if integer >= 0 else default
    except (TypeError, ValueError):
        return default


def _course_cover(course: Course) -> str:
    image = getattr(course, "image", None)
    if image is not None:
        try:
            url = image.url  # type: ignore[attr-defined]
        except (ValueError, AttributeError):
            url = ""
        if url:
            return url
    return PLACEHOLDER_COVER


def _course_url(course: Course) -> str:
    try:
        return course.get_absolute_url()
    except Exception:
        slug = getattr(course, "slug", "")
        return f"/course-detail/{slug}/" if slug else "#"


def _course_progress(course: Course) -> int:
    progress = getattr(course, "progress_pct", None)
    return _clean_int(progress)


def course_list(request, params: Mapping[str, Any]) -> Dict[str, Any]:
    data = dict(params or {})
    limit = _clean_int(data.get("limit"), 12)

    try:
        queryset = Course.objects.published()
    except (OperationalError, ProgrammingError):
        queryset = Course.objects.none()

    if limit:
        queryset = queryset[:limit]

    courses: List[Dict[str, Any]] = []
    for course in queryset:
        courses.append(
            {
                "title": _clean_str(course.title, ""),
                "slug": _clean_str(course.slug, ""),
                "url": _course_url(course),
                "cover_url": _course_cover(course),
                "progress_pct": _course_progress(course),
            }
        )

    ctx: Dict[str, Any] = {
        "limit": limit,
        "list_title": _clean_str(data.get("list_title")),
        "list_subtitle": _clean_str(data.get("list_subtitle")),
        "label_languages": _clean_str(data.get("label_languages")),
        "label_lessons": _clean_str(data.get("label_lessons")),
        "label_score": _clean_str(data.get("label_score")),
        "empty_state_title": _clean_str(data.get("empty_state_title")),
        "empty_state_description": _clean_str(data.get("empty_state_description")),
        "courses": courses,
    }
    return ctx
