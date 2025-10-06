"""Ensure demo media attachment script is idempotent."""
from __future__ import annotations

from pathlib import Path

from django.conf import settings

from apps.catalog.models.models import Course
from apps.common.runscript_harness import binary_harness
from apps.content.models import Lecture, LectureType, Section
from apps.content.scripts import attach_demo_media, seed_stream_demo


MEDIA_ROOT = Path(settings.MEDIA_ROOT)


STREAM_FILES = {
    (1, 1): MEDIA_ROOT / "videos/courses/stream-demo-intro.mp4",
    (1, 2): MEDIA_ROOT / "videos/courses/stream-demo-range.mp4",
    (2, 1): MEDIA_ROOT / "videos/courses/stream-demo-security.mp4",
    (2, 2): MEDIA_ROOT / "videos/courses/stream-demo-monitoring.mp4",
}

GATING_FILES = {
    (1, 1): MEDIA_ROOT / "videos/learning/BigBuckBunny.mp4",
    (1, 2): MEDIA_ROOT / "videos/learning/ElephantsDream.mp4",
    (2, 1): MEDIA_ROOT / "videos/learning/ForBiggerBlazes.mp4",
    (2, 2): MEDIA_ROOT / "videos/learning/ForBiggerEscapes.mp4",
}


def _ensure_gating_course() -> Course:
    course, _ = Course.objects.update_or_create(
        slug="gating-demo",
        defaults={
            "title": "Gating Demo",
            "description": "Verrou démo front/back",
            "is_published": True,
            "free_lectures_count": 2,
        },
    )
    for order in (1, 2):
        Section.objects.update_or_create(
            course=course,
            order=order,
            defaults={"title": f"Section {order}", "is_published": True},
        )

    for (section_order, lecture_order), path in GATING_FILES.items():
        section = Section.objects.get(course=course, order=section_order)
        Lecture.objects.update_or_create(
            course=course,
            section=section,
            order=lecture_order,
            defaults={
                "title": f"Gating {section_order}.{lecture_order}",
                "type": LectureType.VIDEO,
                "is_published": True,
                "is_free": section_order == 1,
                "video_path": "",
                "video_file": None,
            },
        )
    return course


def _clear_video_fields(course: Course) -> None:
    Lecture.objects.filter(course=course).update(video_path="", video_file=None)


@binary_harness
def run(*args, **kwargs):
    seed_stream_demo.run()
    stream_course = Course.objects.get(slug="stream-demo")
    gating_course = _ensure_gating_course()

    _clear_video_fields(stream_course)
    _clear_video_fields(gating_course)

    first = attach_demo_media.run()
    assert first.get("ok"), f"attach_demo_media should succeed, errors={first.get('errors')}"
    assert first.get("created", 0) >= 8, "First run must create links"

    for (section_order, lecture_order), path in STREAM_FILES.items():
        lecture = Lecture.objects.get(
            course=stream_course,
            section__order=section_order,
            order=lecture_order,
        )
        assert Path(lecture.video_path).resolve(strict=False) == path.resolve(strict=False), (
            f"Stream demo lecture {section_order}.{lecture_order} should link {path}"
        )

    for (section_order, lecture_order), path in GATING_FILES.items():
        lecture = Lecture.objects.get(
            course=gating_course,
            section__order=section_order,
            order=lecture_order,
        )
        assert Path(lecture.video_path).resolve(strict=False) == path.resolve(strict=False), (
            f"Gating demo lecture {section_order}.{lecture_order} should link {path}"
        )

    second = attach_demo_media.run()
    assert second.get("created", 0) == 0, "Second run must be idempotent"
    assert second.get("skipped", 0) >= 8, "Second run should report skipped links"

    return {
        "ok": True,
        "name": "test_attach_demo_media_idempotent",
        "duration": 0.0,
        "logs": [
            f"first_created={first.get('created')} skipped={first.get('skipped')}",
            f"second_created={second.get('created')} skipped={second.get('skipped')}",
        ],
    }

