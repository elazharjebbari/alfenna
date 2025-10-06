from __future__ import annotations

import re
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from apps.accounts.scripts import ensure_buyer_fixture
from apps.billing.models import Entitlement
from apps.catalog.models.models import Course
from apps.content.models import Lecture, LectureVideoVariant, LanguageCode
from apps.content.scripts import seed_bougie_multilang

PASSWORD = "Password-2025"
USERNAME = "buyer_access"
COURSE_SLUG = "fabrication-de-bougie"
FREE_PREFIXES = ["1", "1-1", "2", "2-1"]
PREMIUM_PREFIX = "3"
PREFIX_PATTERN = re.compile(r"^(\d+(?:-\d+)?)")
SUFFIX_PATTERN = re.compile(r"[_-][A-Za-z0-9]{4,}$")


def _strip_random_suffix(stem: str) -> str:
    candidate = stem
    while True:
        match = SUFFIX_PATTERN.search(candidate)
        if not match:
            break
        candidate = candidate[: match.start()]
    return candidate


def _prefix_from_lecture(lecture: Lecture) -> str | None:
    stems = []
    for variant in lecture.video_variants.all():
        stems.append(Path(variant.storage_path).stem)
    if lecture.video_path:
        stems.append(Path(lecture.video_path).stem)
    for stem in stems:
        if not stem:
            continue
        match = PREFIX_PATTERN.match(stem)
        if match:
            return match.group(1)
        cleaned = _strip_random_suffix(stem)
        match = PREFIX_PATTERN.match(cleaned)
        if match:
            return match.group(1)
    return None


class BuyerAccessSmokeTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tmp = TemporaryDirectory()
        self.media_root = Path(self.tmp.name)
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()

        fr_dir = self.media_root / "videos" / "stream" / "fr_france"
        ar_dir = self.media_root / "videos" / "stream" / "ar_maroc"
        fr_dir.mkdir(parents=True, exist_ok=True)
        ar_dir.mkdir(parents=True, exist_ok=True)

        samples = {
            "1": "Introduction",
            "1-1": "Démonstration 1",
            "2": "Deuxieme Partie",
            "2-1": "Deuxieme Demo",
            "3": "Premier Module Premium",
        }

        for prefix, name in samples.items():
            stem = f"{prefix}_-_{name.replace(' ', '_')}"
            (fr_dir / f"{stem}.mp4").write_bytes(b"FR" * 10)
            (ar_dir / f"{stem}.mp4").write_bytes(b"AR" * 10)

        seed_bougie_multilang.run()
        ensure_buyer_fixture.run(script_args=[f"password={PASSWORD}"])

    def tearDown(self) -> None:
        self.override.disable()
        self.tmp.cleanup()
        super().tearDown()

    def _lecture_map(self, course: Course) -> dict[str, Lecture]:
        mapping: dict[str, Lecture] = {}
        for lecture in Lecture.objects.filter(course=course).prefetch_related("video_variants", "section"):
            prefix = _prefix_from_lecture(lecture)
            if prefix:
                mapping[prefix] = lecture
        return mapping

    def _head(self, client: Client, lecture: Lecture, lang: str):
        return client.head(
            f"/learning/stream/{lecture.id}/",
            {"lang": lang},
            HTTP_RANGE="bytes=0-1023",
        )

    def _assert_allowed(self, response, lang: str):
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response["Content-Language"].lower(), lang.replace("_", "-").lower())
        self.assertIn("Accept-Language", response.get("Vary", ""))
        self.assertEqual(response["Accept-Ranges"], "bytes")
        self.assertTrue(response["Content-Range"].startswith("bytes 0-"))

    def test_access_flow_for_buyer_access(self):
        course = Course.objects.get(slug=COURSE_SLUG)
        lecture_map = self._lecture_map(course)

        for expected_prefix in FREE_PREFIXES + [PREMIUM_PREFIX]:
            self.assertIn(expected_prefix, lecture_map, f"Prefixe {expected_prefix} manquant")

        user = get_user_model().objects.get(username=USERNAME)
        Entitlement.objects.filter(user=user, course=course).delete()

        client = Client()
        self.assertTrue(client.login(username=USERNAME, password=PASSWORD))

        # Free lectures accessible
        for prefix in FREE_PREFIXES:
            lecture = lecture_map[prefix]
            response_fr = self._head(client, lecture, "fr_FR")
            self._assert_allowed(response_fr, "fr_FR")
            if lecture.video_variants.filter(lang=LanguageCode.AR_MA).exists():
                response_ar = self._head(client, lecture, "ar_MA")
                self._assert_allowed(response_ar, "ar_MA")

        # Premium blocked
        premium_lecture = lecture_map[PREMIUM_PREFIX]
        response_blocked = self._head(client, premium_lecture, "fr_FR")
        self.assertIn(response_blocked.status_code, (302, 403))

        # Grant entitlement and retry
        Entitlement.objects.get_or_create(user=user, course=course)
        client.logout()
        self.assertTrue(client.login(username=USERNAME, password=PASSWORD))

        response_allowed = self._head(client, premium_lecture, "fr_FR")
        self._assert_allowed(response_allowed, "fr_FR")
        if premium_lecture.video_variants.filter(lang=LanguageCode.AR_MA).exists():
            response_allowed_ar = self._head(client, premium_lecture, "ar_MA")
            self._assert_allowed(response_allowed_ar, "ar_MA")

        # Ensure variant defaults are correct (FR default)
        fr_variant = LectureVideoVariant.objects.get(lecture=premium_lecture, lang=LanguageCode.FR_FR)
        self.assertTrue(fr_variant.is_default)
