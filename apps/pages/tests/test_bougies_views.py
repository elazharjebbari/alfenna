from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext, override_settings
from django.urls import reverse

from django.contrib.auth import get_user_model

from apps.content.models import Lecture
from apps.content.scripts import reset_and_load_bougies as loader


@override_settings(
    DISABLE_BOUGIES_AUTOLOAD="1",
)
class BougiesPagesTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.media_root = Path(self.tmp.name)
        (self.media_root / "videos").mkdir(parents=True, exist_ok=True)
        self._make_video("1_intro.mp4", size=128)
        self._make_video("2_cires.mp4", size=128)
        self._make_video("BONUS_final.mp4", size=128)

        settings_override = override_settings(MEDIA_ROOT=str(self.media_root))
        settings_override.enable()
        self.addCleanup(settings_override.disable)

        loader.run(script_args=["--media-root", str(self.media_root), "--apply"])

        User = get_user_model()
        self.user = User.objects.create_user("learner", "learner@example.com", "pass1234")

    def tearDown(self):
        shutil.rmtree(self.tmp.name, ignore_errors=True)

    def _make_video(self, name: str, size: int = 128):
        path = self.media_root / "videos" / name
        path.write_bytes(b"0" * size)
        return path

    def test_learn_requires_authentication(self):
        url = reverse("pages:lecture", kwargs={"course_slug": "bougies-naturelles"})
        response = self.client.get(url)
        self.assertIn(response.status_code, {301, 302})
        self.assertIn("login", response.headers.get("Location", ""))

    def test_learn_lists_all_videos(self):
        self.client.force_login(self.user)
        url = reverse("pages:lecture", kwargs={"course_slug": "bougies-naturelles"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        lecture_count = Lecture.objects.filter(course__slug="bougies-naturelles").count()
        self.assertEqual(response.content.decode().count("data-lecture-id"), lecture_count)

    def test_demo_exposes_only_demo_videos(self):
        url = reverse("pages:demo", kwargs={"course_slug": "bougies-naturelles"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        demo_titles = list(
            Lecture.objects.filter(course__slug="bougies-naturelles", is_demo=True).values_list("title", flat=True)
        )
        other_titles = list(
            Lecture.objects.filter(course__slug="bougies-naturelles", is_demo=False).values_list("title", flat=True)
        )
        for title in demo_titles:
            self.assertIn(title, html)
        for title in other_titles:
            self.assertNotIn(title, html)

    def test_learn_view_queries_within_budget(self):
        self.client.force_login(self.user)
        url = reverse("pages:lecture", kwargs={"course_slug": "bougies-naturelles"})
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(url)
        relevant = [
            q for q in ctx.captured_queries
            if "content_lecture" in q["sql"] or "catalog_course" in q["sql"]
        ]
        self.assertLessEqual(len(relevant), 3)
