"""Audit media links for demo courses."""
from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from django.conf import settings
from django.core.files.storage import default_storage
from django.test import Client
from django.urls import NoReverseMatch, reverse

from apps.catalog.models.models import Course
from apps.common.runscript_harness import binary_harness
from apps.content.models import Lecture, Section
from apps.content.scripts import attach_demo_media, seed_stream_demo


MEDIA_ROOT = Path(settings.MEDIA_ROOT)


@dataclass
class LectureExpectation:
    section_order: int
    lecture_order: int


EXPECTATIONS: Dict[str, List[LectureExpectation]] = {
    "stream-demo": [
        LectureExpectation(1, 1),
        LectureExpectation(1, 2),
        LectureExpectation(2, 1),
        LectureExpectation(2, 2),
    ],
    "gating-demo": [
        LectureExpectation(1, 1),
        LectureExpectation(1, 2),
        LectureExpectation(2, 1),
        LectureExpectation(2, 2),
    ],
}


def _field_file_url(field) -> str | None:
    if not field:
        return None
    try:
        return field.url or None
    except Exception:
        return None


def _field_file_storage_path(field) -> str | None:
    if not field:
        return None
    name = getattr(field, "name", "") or ""
    return name or None


def _as_path(raw: str | None) -> Path | None:
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    return MEDIA_ROOT / candidate


def _file_ok(path: Path) -> Tuple[bool, str]:
    if not path.exists():
        return False, "missing"
    if not path.is_file():
        return False, "not-a-file"
    if path.stat().st_size <= 0:
        return False, "empty"
    mime, _ = mimetypes.guess_type(path.name)
    if not (mime and mime.startswith("video/")):
        return False, "mime"
    return True, "ok"


def _resolve_source(lecture: Lecture) -> Tuple[bool, str, str]:
    """Return (ok, source_name, detail)."""

    # 1) lecture.video.file.url
    video_rel = getattr(lecture, "video", None)
    file_candidate = getattr(video_rel, "file", None)
    url = _field_file_url(file_candidate)
    if url:
        storage_path = _field_file_storage_path(file_candidate)
        if storage_path and default_storage.exists(storage_path):
            mime, _ = mimetypes.guess_type(storage_path)
            if mime and mime.startswith("video/"):
                return True, "video.file", storage_path
            return False, "video.file", f"mime:{mime or 'unknown'}"
        return False, "video.file", "storage-missing"

    # 2) lecture.video_url
    direct_url = getattr(lecture, "video_url", "") or ""
    if direct_url.strip():
        mime, _ = mimetypes.guess_type(direct_url)
        if mime and mime.startswith("video/"):
            return True, "video_url", direct_url.strip()
        return True, "video_url", direct_url.strip()

    # 3) lecture.file.url (legacy document field)
    doc_url = _field_file_url(getattr(lecture, "file", None))
    if doc_url:
        mime, _ = mimetypes.guess_type(doc_url)
        if mime and mime.startswith("video/"):
            return True, "file.url", doc_url
        return False, "file.url", f"mime:{mime or 'unknown'}"

    # 4) lecture.video_file.video_file.url
    nested = _field_file_url(getattr(getattr(lecture, "video_file", None), "video_file", None))
    if nested:
        mime, _ = mimetypes.guess_type(nested)
        if mime and mime.startswith("video/"):
            return True, "video_file.video_file", nested
        return False, "video_file.video_file", f"mime:{mime or 'unknown'}"

    # 5) lecture.video_file (FieldFile)
    lecture_file = getattr(lecture, "video_file", None)
    file_name = _field_file_storage_path(lecture_file)
    if file_name:
        if default_storage.exists(file_name):
            mime, _ = mimetypes.guess_type(file_name)
            if mime and mime.startswith("video/"):
                return True, "video_file", file_name
            return False, "video_file", f"mime:{mime or 'unknown'}"
        return False, "video_file", "storage-missing"

    # 6) lecture.video_path string
    raw_path = getattr(lecture, "video_path", "")
    candidate = _as_path(raw_path)
    if candidate:
        ok, reason = _file_ok(candidate)
        if ok:
            return True, "video_path", str(candidate)
        return False, "video_path", reason

    # 7) fallback to stream endpoint
    try:
        url = reverse("learning:stream", args=[lecture.pk])
    except NoReverseMatch:
        return False, "stream", "no-route"

    client = Client()
    resp = client.head(url)
    if resp.status_code == 206:
        return True, "stream", "head-206"
    return False, "stream", f"status:{resp.status_code}"


@binary_harness
def run(*args, **kwargs):
    seed_stream_demo.run()
    attach_demo_media.run()

    logs: List[str] = []
    failures: List[str] = []

    for slug, entries in EXPECTATIONS.items():
        course = Course.objects.filter(slug=slug).first()
        if not course:
            failures.append(f"course-missing:{slug}")
            continue

        course_ok = True
        for entry in entries:
            section = Section.objects.filter(course=course, order=entry.section_order).first()
            if not section:
                failures.append(f"section-missing:{slug}:{entry.section_order}")
                course_ok = False
                continue

            lecture = (
                Lecture.objects.filter(section=section, order=entry.lecture_order)
                .select_related("section")
                .first()
            )
            if not lecture:
                failures.append(
                    f"lecture-missing:{slug}:{entry.section_order}.{entry.lecture_order}"
                )
                course_ok = False
                continue

            ok, source, detail = _resolve_source(lecture)
            if not ok:
                failures.append(
                    f"lecture-source:{slug}:{entry.section_order}.{entry.lecture_order}:{source}:{detail}"
                )
                course_ok = False

        status = "OK" if course_ok else "KO"
        logs.append(f"course {slug}: {status}")

    for line in logs:
        print(line)
    for err in failures:
        print(f"  - {err}")

    return {
        "ok": not failures,
        "name": "test_media_integrity_links",
        "duration": 0.0,
        "logs": logs,
        "errors": failures,
    }

