from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import override_settings

from apps.catalog.models.models import Course
from apps.content.models import Lecture, LectureType, Section, LectureVideoVariant, LanguageCode
from apps.content.scripts import ingest_multilang_variants
from apps.common.runscript_harness import binary_harness


def _write_video(media_root: Path, relative: str) -> None:
    path = media_root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"Z" * 1024)


def _setup_course() -> Lecture:
    course, _ = Course.objects.update_or_create(
        slug="bougies-naturelles",
        defaults={
            "title": "Bougies",
            "description": "",
            "is_published": True,
        },
    )
    section, _ = Section.objects.update_or_create(
        course=course,
        order=1,
        defaults={"title": "Intro", "is_published": True},
    )
    lecture, _ = Lecture.objects.update_or_create(
        course=course,
        section=section,
        order=1,
        defaults={
            "title": "Introduction et présentation du matériel",
            "type": LectureType.VIDEO,
            "is_published": True,
        },
    )
    return lecture


@binary_harness
def run():  # pragma: no cover - executed via runscript harness
    tmp = TemporaryDirectory()
    media_root = Path(tmp.name)
    lecture = _setup_course()

    fr_rel = "videos/stream/fr_france/1_-_Introduction_et_presentation_du_materiel.mp4"
    ar_rel = "videos/strem/ar_maroc/1_-_Introduction_et_presentation_du_materiel.mp4"
    _write_video(media_root, fr_rel)
    _write_video(media_root, ar_rel)

    try:
        with override_settings(MEDIA_ROOT=media_root):
            LectureVideoVariant.objects.filter(lecture=lecture).delete()

            dry_res = ingest_multilang_variants.run(script_args=["course_slug=bougies-naturelles"])
            payload = dry_res["logs"][0]["summary"]
            assert payload["dry_run"], "Dry-run should be flagged"
            assert payload["create"] == 2, "Expected two variants in dry-run"
            assert LectureVideoVariant.objects.filter(lecture=lecture).count() == 0, "Dry-run must not persist variants"

            apply_res = ingest_multilang_variants.run(script_args=["course_slug=bougies-naturelles", "--apply"])
            assert LectureVideoVariant.objects.filter(lecture=lecture).count() == 2, "Apply should create variants"
            assert apply_res["logs"][0]["summary"]["create"] == 2, "First apply should report creations"

            second = ingest_multilang_variants.run(script_args=["course_slug=bougies-naturelles", "--apply"])
            assert LectureVideoVariant.objects.filter(lecture=lecture).count() == 2, "Second apply should be idempotent"
            summary_again = second["logs"][0]["summary"]
            assert summary_again["create"] == 0, "Second apply should report zero creations"
            assert summary_again["update"] == 0, "Second apply should report zero updates"
            assert summary_again["noop"] >= 2, "Second apply should mark existing variants as noops"

            langs = set(LectureVideoVariant.objects.filter(lecture=lecture).values_list("lang", flat=True))
            assert langs == {LanguageCode.FR_FR, LanguageCode.AR_MA}, "Variants should cover FR and AR"
    finally:
        tmp.cleanup()

    return {
        "ok": True,
        "name": "test_ingest_multilang",
        "duration": 0.0,
        "logs": [],
    }
