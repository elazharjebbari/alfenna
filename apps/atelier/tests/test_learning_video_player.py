from __future__ import annotations

from types import SimpleNamespace

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase
from django.urls import reverse, NoReverseMatch

from apps.atelier.compose.hydrators.learning.hydrators import video_player
from apps.catalog.models.models import Course
from apps.content.models import LanguageCode, Lecture, LectureType, LectureVideoVariant, Section


class VideoPlayerHydratorTests(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.course = Course.objects.create(
            title="Bougies",
            slug="bougies-naturelles",
            description="",
            is_published=True,
            free_lectures_count=1,
        )
        self.section = Section.objects.create(course=self.course, title="Intro", order=1)
        self.lecture = Lecture.objects.create(
            course=self.course,
            section=self.section,
            title="Bienvenue",
            order=1,
            type=LectureType.VIDEO,
            is_published=True,
            is_free=True,
        )
        self.other_lecture = Lecture.objects.create(
            course=self.course,
            section=self.section,
            title="Chapitre 2",
            order=2,
            type=LectureType.VIDEO,
            is_published=True,
        )
        LectureVideoVariant.objects.create(
            lecture=self.lecture,
            lang=LanguageCode.FR_FR,
            storage_path="videos/stream/fr_france/bienvenue.mp4",
            is_default=True,
        )
        LectureVideoVariant.objects.create(
            lecture=self.lecture,
            lang=LanguageCode.AR_MA,
            storage_path="videos/strem/ar_maroc/bienvenue.mp4",
        )

    def _make_request(self, lecture_slug: str, lang: str | None = None):
        params = {"lang": lang} if lang else {}
        try:
            path = reverse("pages:lecture-detail", kwargs={
                "course_slug": self.course.slug,
                "lecture_slug": lecture_slug,
            })
        except NoReverseMatch:
            path = f"/learn/{self.course.slug}/{lecture_slug}/"
        request = self.factory.get(path, params)
        request.user = AnonymousUser()
        request.resolver_match = SimpleNamespace(kwargs={
            "course_slug": self.course.slug,
            "lecture_slug": lecture_slug,
        })
        return request

    def test_video_player_exposes_variants_and_default_lang(self):
        request = self._make_request(f"s1-l1-bienvenue")
        ctx = video_player(request, {})

        expected_base = reverse("learning:stream", args=[self.lecture.pk])
        self.assertEqual(ctx["active_lang"], LanguageCode.FR_FR)
        self.assertEqual(ctx["stream_url"], f"{expected_base}?lang={LanguageCode.FR_FR}")
        self.assertEqual(ctx["video_variants"], {
            LanguageCode.FR_FR: f"{expected_base}?lang={LanguageCode.FR_FR}",
            LanguageCode.AR_MA: f"{expected_base}?lang={LanguageCode.AR_MA}",
        })
        self.assertFalse(ctx["is_locked"])

    def test_video_player_uses_requested_lang_when_available(self):
        request = self._make_request("s1-l1-bienvenue", lang=LanguageCode.AR_MA)
        ctx = video_player(request, {})

        expected_base = reverse("learning:stream", args=[self.lecture.pk])
        self.assertEqual(ctx["active_lang"], LanguageCode.AR_MA)
        self.assertEqual(ctx["stream_url"], f"{expected_base}?lang={LanguageCode.AR_MA}")

    def test_locked_lecture_does_not_expose_stream_url(self):
        request = self._make_request("s1-l2-chapitre-2")
        ctx = video_player(request, {})

        self.assertTrue(ctx["is_locked"])
        self.assertIsNone(ctx["stream_url"])
        self.assertEqual(ctx["video_variants"], {})
