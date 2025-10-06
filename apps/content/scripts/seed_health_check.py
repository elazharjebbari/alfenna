from __future__ import annotations

from collections import Counter

from django.core.files.storage import default_storage

from apps.catalog.models.models import Course
from apps.common.runscript_harness import binary_harness, skip
from apps.content.models import Lecture, Section


@binary_harness
def run(*args, **kwargs):
    course_slug = kwargs.get("course_slug") or "bougies-naturelles"
    try:
        course = Course.objects.get(slug=course_slug)
    except Course.DoesNotExist:
        return skip(f"course {course_slug} not found")

    sections = Section.objects.filter(course=course, is_published=True).order_by("order")
    lectures = Lecture.objects.filter(course=course, is_published=True).order_by("section__order", "order")

    if not sections.exists() or not lectures.exists():
        return {
            "ok": False,
            "name": "seed_health_check",
            "duration": 0.0,
            "logs": ["course missing sections or lectures"],
        }

    free_count = lectures.filter(is_free=True).count()
    duplicates = [
        key for key, count in Counter((lec.section_id, lec.order) for lec in lectures).items() if count > 1
    ]

    missing_files = []
    for lecture in lectures:
        video_path = (lecture.video_path or "").strip()
        if not video_path:
            missing_files.append(lecture.pk)
            continue
        if not default_storage.exists(video_path):
            missing_files.append(lecture.pk)

    ok = not duplicates and not missing_files and free_count >= 1
    ok = ok and free_count == course.free_lectures_count

    logs = {
        "sections": sections.count(),
        "lectures": lectures.count(),
        "free_count": free_count,
        "course_free_count": course.free_lectures_count,
        "duplicates": duplicates,
        "missing_files": missing_files,
    }

    return {
        "ok": ok,
        "name": "seed_health_check",
        "duration": 0.0,
        "logs": [logs],
    }
