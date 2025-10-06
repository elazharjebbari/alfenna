from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import Client, override_settings
from django.urls import reverse

from apps.catalog.models.models import Course
from apps.content.models import Lecture, LectureType, LectureVideoVariant, Section, LanguageCode
from apps.common.runscript_harness import binary_harness


def _write_video(media_root: Path, relative: str, size: int = 2048) -> None:
    path = media_root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (b"ABCDEFGHIJKLMNOPQRSTUVWXYZ" * ((size // 26) + 1))[:size]
    path.write_bytes(data)


def _setup_course() -> Lecture:
    Course.objects.filter(slug="smoke-multilang").delete()
    course = Course.objects.create(
        title="Smoke Multilang",
        slug="smoke-multilang",
        description="",
        is_published=True,
        free_lectures_count=5,
    )
    section = Section.objects.create(course=course, title="Section 1", order=1)
    lecture = Lecture.objects.create(
        course=course,
        section=section,
        title="Lecture multilang",
        order=1,
        type=LectureType.VIDEO,
        is_published=True,
        is_free=True,
    )
    return lecture


@binary_harness
def run():  # pragma: no cover
    tmp = TemporaryDirectory()
    media_root = Path(tmp.name)
    lecture = _setup_course()

    fr_rel = "videos/stream/fr_france/smoke_fr.mp4"
    ar_rel = "videos/strem/ar_maroc/smoke_ar.mp4"
    _write_video(media_root, fr_rel)
    _write_video(media_root, ar_rel)

    LectureVideoVariant.objects.filter(lecture=lecture).delete()
    LectureVideoVariant.objects.create(
        lecture=lecture,
        lang=LanguageCode.FR_FR,
        storage_path=fr_rel,
        is_default=True,
    )
    LectureVideoVariant.objects.create(
        lecture=lecture,
        lang=LanguageCode.AR_MA,
        storage_path=ar_rel,
    )

    client = Client()
    url = reverse("learning:stream", args=[lecture.pk])

    try:
        with override_settings(MEDIA_ROOT=media_root):
            resp_fr = client.get(url, {"lang": LanguageCode.FR_FR}, HTTP_RANGE="bytes=0-127")
            assert resp_fr.status_code == 206, f"FR stream expected 206, got {resp_fr.status_code}"
            assert resp_fr["Content-Language"] == "fr-FR", f"FR Content-Language unexpected: {resp_fr['Content-Language']}"
            assert "Content-Range" in resp_fr and resp_fr["Content-Range"].startswith("bytes 0-"), "FR Content-Range missing"

            resp_ar = client.get(url, {"lang": LanguageCode.AR_MA}, HTTP_RANGE="bytes=0-127")
            assert resp_ar.status_code == 206, f"AR stream expected 206, got {resp_ar.status_code}"
            assert resp_ar["Content-Language"] == "ar-MA", f"AR Content-Language unexpected: {resp_ar['Content-Language']}"
            assert "Content-Range" in resp_ar and resp_ar["Content-Range"].startswith("bytes 0-"), "AR Content-Range missing"
    finally:
        tmp.cleanup()
        lecture.course.delete()

    return {"ok": True, "name": "test_stream_range_lang_smoke", "duration": 0.0, "logs": []}
