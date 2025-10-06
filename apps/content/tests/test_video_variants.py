from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from django.db import IntegrityError
from django.test import TestCase, override_settings

from apps.catalog.models.models import Course
from apps.content.models import (
    Lecture,
    LectureType,
    Section,
    LectureVideoVariant,
    LanguageCode,
)
from apps.content.scripts import ingest_multilang_variants


class LectureVideoVariantModelTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(title="Test", slug="test", description="", is_published=True)
        self.section = Section.objects.create(course=self.course, title="S1", order=1)
        self.lecture = Lecture.objects.create(
            course=self.course,
            section=self.section,
            title="L1",
            order=1,
            type=LectureType.VIDEO,
        )

    def test_creates_variant(self):
        variant = LectureVideoVariant.objects.create(
            lecture=self.lecture,
            lang=LanguageCode.FR_FR,
            storage_path="videos/stream/fr_france/video.mp4",
        )
        self.assertEqual(variant.path_in_storage(), "videos/stream/fr_france/video.mp4")
        self.assertEqual(variant.lang, LanguageCode.FR_FR)

    def test_unique_per_lecture_and_lang(self):
        LectureVideoVariant.objects.create(
            lecture=self.lecture,
            lang=LanguageCode.FR_FR,
            storage_path="videos/stream/fr_france/video.mp4",
        )
        with self.assertRaises(IntegrityError):
            LectureVideoVariant.objects.create(
                lecture=self.lecture,
                lang=LanguageCode.FR_FR,
                storage_path="videos/stream/fr_france/other.mp4",
            )

    def test_path_prefers_file_field(self):
        variant = LectureVideoVariant.objects.create(
            lecture=self.lecture,
            lang=LanguageCode.AR_MA,
            storage_path="ignored/path.mp4",
        )
        variant.file.name = "videos/storage/file.mp4"
        self.assertEqual(variant.path_in_storage(), "videos/storage/file.mp4")


class IngestMultilangScriptUnitTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.media_root = Path(self.tmp.name)
        self.course = Course.objects.create(
            title="Bougies",
            slug="bougies-test",
            description="",
            is_published=True,
        )
        self.section = Section.objects.create(course=self.course, title="Intro", order=1)
        self.lecture = Lecture.objects.create(
            course=self.course,
            section=self.section,
            title="Introduction",
            order=1,
            type=LectureType.VIDEO,
            is_published=True,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _write_file(self, relative: str):
        path = self.media_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"0" * 1024)

    def test_script_creates_variants_and_is_idempotent(self):
        fr_rel = "videos/stream/fr_france/1_-_introduction.mp4"
        ar_rel = "videos/strem/ar_maroc/1_-_introduction.mp4"
        self._write_file(fr_rel)
        self._write_file(ar_rel)

        with override_settings(MEDIA_ROOT=self.media_root):
            LectureVideoVariant.objects.all().delete()

            dry_res = ingest_multilang_variants.run(script_args=["course_slug=bougies-test"])
            summary = dry_res["logs"][0]["summary"]
            self.assertTrue(summary["dry_run"])
            self.assertEqual(summary["create"], 2)
            self.assertEqual(LectureVideoVariant.objects.count(), 0)

            apply_res = ingest_multilang_variants.run(script_args=["course_slug=bougies-test", "--apply"])
            summary_apply = apply_res["logs"][0]["summary"]
            self.assertEqual(summary_apply["create"], 2)
            self.assertEqual(LectureVideoVariant.objects.count(), 2)

            again = ingest_multilang_variants.run(script_args=["course_slug=bougies-test", "--apply"])
            summary_again = again["logs"][0]["summary"]
            self.assertEqual(summary_again["create"], 0)
            self.assertEqual(summary_again["update"], 0)
            self.assertGreaterEqual(summary_again["noop"], 2)
