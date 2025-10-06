from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.catalog.models.models import Course
from apps.content.models import (
    LanguageCode,
    Lecture,
    LectureType,
    LectureVideoVariant,
    Section,
)
from apps.billing.models import Entitlement


class VideoStreamMultilangTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self._tmp = TemporaryDirectory()
        self.media_root = Path(self._tmp.name)
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(self._tmp.cleanup)

        self.course = Course.objects.create(
            title="Bougies",
            slug="bougies-test",
            description="",
            is_published=True,
            free_lectures_count=5,
        )
        self.section = Section.objects.create(course=self.course, title="Intro", order=1)

    def _make_lecture(self, order: int = 1) -> Lecture:
        lecture = Lecture.objects.create(
            course=self.course,
            section=self.section,
            title=f"Lecture {order}",
            order=order,
            type=LectureType.VIDEO,
            is_published=True,
            is_free=True,
        )
        return lecture

    def _write_file(self, relative_path: str, size: int = 2048) -> Path:
        target = self.media_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        pattern = (b"0123456789" * ((size // 10) + 1))[:size]
        target.write_bytes(pattern)
        return target

    def test_stream_variant_with_lang_query_sets_headers(self):
        lecture = self._make_lecture()
        self._write_file("videos/stream/fr_france/test_fr.mp4", size=2048)
        LectureVideoVariant.objects.create(
            lecture=lecture,
            lang=LanguageCode.FR_FR,
            storage_path="videos/stream/fr_france/test_fr.mp4",
            is_default=True,
        )
        from django.core.files.storage import default_storage
        self.assertTrue(default_storage.exists("videos/stream/fr_france/test_fr.mp4"))
        url = reverse("learning:stream", args=[lecture.pk])
        response = self.client.get(url, {"lang": LanguageCode.FR_FR}, HTTP_RANGE="bytes=0-9")

        self.assertEqual(response.status_code, 206)
        self.assertEqual(response["Content-Language"], "fr-FR")
        self.assertIn("Accept-Language", response["Vary"])
        self.assertIn("bytes 0-9/", response["Content-Range"])
        self.assertEqual(int(response["Content-Length"]), 10)
        content = b"".join(response.streaming_content)
        self.assertEqual(len(content), 10)

    def test_stream_uses_accept_language_when_param_missing(self):
        lecture = self._make_lecture(order=2)
        self._write_file("videos/strem/ar_maroc/test_ar.mp4", size=1024)
        self._write_file("videos/stream/fr_france/test_fr.mp4", size=1024)
        LectureVideoVariant.objects.create(
            lecture=lecture,
            lang=LanguageCode.FR_FR,
            storage_path="videos/stream/fr_france/test_fr.mp4",
            is_default=True,
        )
        LectureVideoVariant.objects.create(
            lecture=lecture,
            lang=LanguageCode.AR_MA,
            storage_path="videos/strem/ar_maroc/test_ar.mp4",
        )
        url = reverse("learning:stream", args=[lecture.pk])
        response = self.client.get(url, HTTP_RANGE="bytes=0-4", HTTP_ACCEPT_LANGUAGE="ar,fr;q=0.8")

        self.assertEqual(response.status_code, 206)
        self.assertEqual(response["Content-Language"], "ar-MA")
        self.assertIn("bytes 0-", response["Content-Range"])

    def test_stream_falls_back_to_default_video(self):
        lecture = self._make_lecture(order=3)
        self._write_file("videos/base.mp4", size=512)
        lecture.video_path = "videos/base.mp4"
        lecture.save(update_fields=["video_path"])
        url = reverse("learning:stream", args=[lecture.pk])
        response = self.client.get(url, {"lang": LanguageCode.AR_MA}, HTTP_RANGE="bytes=0-99")

        self.assertEqual(response.status_code, 206)
        self.assertEqual(response["Content-Language"], "fr-FR")
        self.assertIn("/512", response["Content-Range"])

    def test_premium_requires_entitlement(self):
        premium = Lecture.objects.create(
            course=self.course,
            section=self.section,
            title="Premium",
            order=99,
            type=LectureType.VIDEO,
            is_published=True,
            is_free=False,
        )
        self.course.free_lectures_count = 0
        self.course.save(update_fields=["free_lectures_count"])
        self._write_file("videos/premium.mp4", size=512)
        premium.video_path = "videos/premium.mp4"
        premium.save(update_fields=["video_path"])

        url = reverse("learning:stream", args=[premium.pk])

        User = get_user_model()
        user = User.objects.create_user(username="premium-tester", password="p@ss12345", email="p@example.com")
        self.client.login(username="premium-tester", password="p@ss12345")

        # Auth sans entitlement → redirection vers la page cours
        response_locked = self.client.get(url, HTTP_RANGE="bytes=0-9")
        self.assertEqual(response_locked.status_code, 302)
        self.assertIn(self.course.slug, response_locked.url)

        Entitlement.objects.create(user=user, course=self.course)

        response_ok = self.client.get(url, HTTP_RANGE="bytes=0-9")
        self.assertEqual(response_ok.status_code, 206)
        self.assertIn("bytes 0-9", response_ok["Content-Range"])
