"""Seed d'un cours streaming de démonstration."""
from __future__ import annotations

import shutil
from pathlib import Path

from django.conf import settings

from apps.catalog.models.models import Course, CoursePrice
from apps.content.models import Lecture, LectureType, Section
from apps.common.runscript_harness import binary_harness


MINIMAL_MP4 = (
    b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
    b"\x00\x00\x00\x08free\x00\x00\x02\x00mdat"
    + b"\x00" * 2048
)


def _ensure_demo_video(filename: str) -> Path:
    media_root = Path(settings.MEDIA_ROOT)
    target = media_root / "videos" / "courses" / filename
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists():
        return target

    # Essaye de réutiliser une vidéo exemple si disponible.
    sample_dir = media_root / "videos"
    sample_candidates = list(sample_dir.glob("**/*.mp4"))
    sample = next((p for p in sample_candidates if p.is_file()), None)

    if sample:
        shutil.copyfile(sample, target)
    else:
        target.write_bytes(MINIMAL_MP4)

    return target


@binary_harness
def run(*args, **kwargs):
    print("== seed_stream_demo: start ==")

    course, created = Course.objects.update_or_create(
        slug="stream-demo",
        defaults={
            "title": "Streaming Demo",
            "description": "Parcours démonstration pour valider le streaming vidéo backend.",
            "seo_title": "Streaming Demo",
            "seo_description": "Stream HTTP Range 206 — cours de démonstration.",
            "difficulty": "beginner",
            "free_lectures_count": 2,
            "is_published": True,
        },
    )

    sections_data = [
        (1, "Préparer le streaming"),
        (2, "Streaming avancé"),
    ]
    sections = {}
    for order, title in sections_data:
        section, _ = Section.objects.update_or_create(
            course=course,
            order=order,
            defaults={
                "title": title,
                "is_published": True,
            },
        )
        sections[order] = section

    lectures_data = [
        (1, 1, "Bienvenue dans la démo", True, "stream-demo-intro.mp4"),
        (1, 2, "Comprendre Range 206", True, "stream-demo-range.mp4"),
        (2, 1, "Sécuriser le flux", False, "stream-demo-security.mp4"),
        (2, 2, "Monitoring et logs", False, "stream-demo-monitoring.mp4"),
    ]

    for section_order, lecture_order, title, is_free, filename in lectures_data:
        video_path = str(_ensure_demo_video(filename))
        Section.objects.filter(pk=sections[section_order].pk).update(is_published=True)
        Lecture.objects.update_or_create(
            section=sections[section_order],
            order=lecture_order,
            defaults={
                "course": course,
                "title": title,
                "type": LectureType.VIDEO,
                "is_published": True,
                "is_free": is_free,
                "video_path": video_path,
                "video_file": None,
            },
        )

    CoursePrice.objects.update_or_create(
        course=course,
        currency="EUR",
        country=None,
        defaults={
            "amount_cents": 16900,
            "active": True,
        },
    )
    CoursePrice.objects.update_or_create(
        course=course,
        currency="USD",
        country=None,
        defaults={
            "amount_cents": 17900,
            "active": True,
        },
    )

    for other in Course.objects.filter(is_published=True):
        for currency, cents in (("EUR", 16900), ("USD", 17900)):
            CoursePrice.objects.get_or_create(
                course=other,
                currency=currency,
                country=None,
                defaults={
                    "amount_cents": cents,
                    "active": True,
                },
            )

    print(f"Seed OK — course_id={course.id} created={created}")
    print("== seed_stream_demo: OK ✅ ==")
    return {"ok": True, "name": "seed_stream_demo", "duration": 0.0, "logs": []}
