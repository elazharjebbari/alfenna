"""Attach demo video files to seeded demo courses."""
from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from django.conf import settings
from django.db import transaction

from apps.catalog.models.models import Course
from apps.common.runscript_harness import binary_harness
from apps.content.models import Lecture, LectureType, Section


@dataclass(frozen=True)
class LectureTarget:
    section_order: int
    lecture_order: int
    file_path: Path


MEDIA_ROOT = Path(settings.MEDIA_ROOT)


def _media_path(relative: str) -> Path:
    candidate = Path(relative)
    return candidate if candidate.is_absolute() else MEDIA_ROOT / relative


def _build_targets() -> Dict[str, List[LectureTarget]]:
    courses: Dict[str, List[Tuple[int, int, str]]] = {
        "stream-demo": [
            (1, 1, "videos/courses/stream-demo-intro.mp4"),
            (1, 2, "videos/courses/stream-demo-range.mp4"),
            (2, 1, "videos/courses/stream-demo-security.mp4"),
            (2, 2, "videos/courses/stream-demo-monitoring.mp4"),
        ],
        "gating-demo": [
            (1, 1, "videos/learning/BigBuckBunny.mp4"),
            (1, 2, "videos/learning/ElephantsDream.mp4"),
            (2, 1, "videos/learning/ForBiggerBlazes.mp4"),
            (2, 2, "videos/learning/ForBiggerEscapes.mp4"),
        ],
    }
    return {
        slug: [LectureTarget(sec, lec, _media_path(path)) for sec, lec, path in entries]
        for slug, entries in courses.items()
    }


def _ensure_sections(course: Course, targets: Iterable[LectureTarget]) -> None:
    missing_sections: Dict[int, str] = {}
    for target in targets:
        missing_sections.setdefault(target.section_order, f"Section {target.section_order}")
    for order in sorted(missing_sections):
        Section.objects.get_or_create(
            course=course,
            order=order,
            defaults={"title": missing_sections[order], "is_published": True},
        )


def _validate_file(path: Path) -> Tuple[bool, str]:
    if not path.exists():
        return False, "missing"
    if not path.is_file():
        return False, "not-a-file"
    size = path.stat().st_size
    if size <= 0:
        return False, "empty"
    mime, _ = mimetypes.guess_type(path.name)
    if not (mime and mime.startswith("video/")):
        return False, "mime"
    return True, "ok"


def _normalise(value: str | None) -> str:
    return (value or "").strip()


def _to_abs_path(raw: str | None) -> Path | None:
    cleaned = _normalise(raw)
    if not cleaned:
        return None
    candidate = Path(cleaned)
    if candidate.is_absolute():
        return candidate.resolve(strict=False)
    return (MEDIA_ROOT / candidate).resolve(strict=False)


@binary_harness
def run(*args, **kwargs):
    targets = _build_targets()
    created = 0
    skipped = 0
    errors: List[str] = []

    for slug, lecture_targets in targets.items():
        course = Course.objects.filter(slug=slug).first()
        if not course:
            errors.append(f"course-missing:{slug}")
            continue

        _ensure_sections(course, lecture_targets)
        with transaction.atomic():
            for entry in lecture_targets:
                section = Section.objects.filter(course=course, order=entry.section_order).first()
                if not section:
                    errors.append(f"section-missing:{slug}:{entry.section_order}")
                    continue

                lecture = Lecture.objects.filter(section=section, order=entry.lecture_order).first()
                if not lecture:
                    title = f"Lecture {entry.section_order}.{entry.lecture_order}"
                    lecture = Lecture.objects.create(
                        course=course,
                        section=section,
                        order=entry.lecture_order,
                        title=title,
                        type=LectureType.VIDEO,
                        is_published=True,
                    )

                ok, reason = _validate_file(entry.file_path)
                if not ok:
                    errors.append(f"file-{reason}:{entry.file_path}")
                    continue

                target_value = str(entry.file_path)
                current_abs = _to_abs_path(lecture.video_path)
                target_abs = entry.file_path.resolve(strict=False)
                if current_abs and current_abs == target_abs:
                    skipped += 1
                    continue

                lecture.type = LectureType.VIDEO
                lecture.video_path = target_value
                lecture.video_file = None
                lecture.save(update_fields=["type", "video_path", "video_file", "updated_at"])
                created += 1

    ok = not errors
    status = "OK" if ok else "KO"
    print(
        f"attach_demo_media: {status} created={created} skipped={skipped} errors={len(errors)}",
        flush=True,
    )
    for err in errors:
        print(f"  - {err}")

    return {
        "ok": ok,
        "name": "attach_demo_media",
        "created": created,
        "skipped": skipped,
        "errors": errors,
    }
