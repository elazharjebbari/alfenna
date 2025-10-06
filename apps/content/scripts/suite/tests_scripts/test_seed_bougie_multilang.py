from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import override_settings

from apps.catalog.models.models import Course
from apps.content.models import Lecture, LectureVideoVariant
from apps.content.scripts import seed_bougie_multilang
from apps.common.runscript_harness import binary_harness
from apps.content.scripts.seed_bougie_multilang import COURSE_SLUG, _collect_prefix_infos


def _write_dummy(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"0" * 1024)


@binary_harness
def run():  # pragma: no cover - executed via runscript harness
    tmp = TemporaryDirectory()
    media_root = Path(tmp.name)
    fr_dir = media_root / "videos" / "stream" / "fr_france"
    ar_dir = media_root / "videos" / "stream" / "ar_maroc"

    fr_file = fr_dir / "1_-_Introduction_et_presentation.mp4"
    ar_file = ar_dir / "1_-_Introduction_et_presentation.mp4"
    fr_bonus = fr_dir / "2-1_-_Formule_avancee.mp4"
    ar_bonus = ar_dir / "2-1_-_Formule_avancee.mp4"
    _write_dummy(fr_file)
    _write_dummy(ar_file)
    _write_dummy(fr_bonus)
    _write_dummy(ar_bonus)

    try:
        with override_settings(MEDIA_ROOT=media_root):
            Course.objects.filter(slug=COURSE_SLUG).delete()
            infos = _collect_prefix_infos(media_root)
            assert set(infos.keys()) == {"1", "2-1"}

            first = seed_bougie_multilang.run()
            assert first["ok"], "First seed should succeed"

            course = Course.objects.get(slug=COURSE_SLUG)
            assert course.free_lectures_count == 2

            lectures = Lecture.objects.filter(course=course)
            lecture_count = lectures.count()
            assert lecture_count >= 2, "At least two lectures should be created"

            variants = LectureVideoVariant.objects.filter(lecture__course=course)
            variant_count = variants.count()
            assert variant_count == 4, "Expected two languages for two prefixes"
            fr_variant = variants.get(lang="fr_FR", storage_path=str(fr_file.relative_to(media_root)).replace("\\", "/"))
            assert fr_variant.is_default is True
            assert fr_variant.lecture.is_free is True

            # Ensure idempotence (course recreated cleanly)
            second = seed_bougie_multilang.run()
            assert second["ok"], "Second seed should succeed"
            course_second = Course.objects.get(slug=COURSE_SLUG)
            assert Lecture.objects.filter(course=course_second).count() == lecture_count
            assert LectureVideoVariant.objects.filter(lecture__course=course_second).count() == variant_count
    finally:
        tmp.cleanup()

    return {"ok": True, "name": "test_seed_bougie_multilang", "duration": 0.0, "logs": []}
