from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import TestCase, override_settings

from apps.catalog.models.models import Course
from apps.content.models import Lecture
from apps.content.scripts import seed_from_videos as seed_mod
from apps.content.scripts import reset_and_load_bougies as loader


class SeedFromVideosTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.media_root = Path(self.tmp.name)

    def tearDown(self):
        shutil.rmtree(self.tmp.name, ignore_errors=True)

    def _make_file(self, name: str, size: int = 100) -> Path:
        path = self.media_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"0" * size)
        return path

    def test_resolve_source_dir_accepts_media_prefix(self):
        videos_dir = self.media_root / "videos"
        videos_dir.mkdir(parents=True, exist_ok=True)

        resolved_default = seed_mod._resolve_source_dir(self.media_root, "videos")
        resolved_prefixed = seed_mod._resolve_source_dir(self.media_root, "media/videos")

        self.assertEqual(resolved_default, videos_dir.resolve())
        self.assertEqual(resolved_prefixed, videos_dir.resolve())

    def test_pick_files_prefers_unsuffixed_and_largest(self):
        self._make_file("videos/1_intro.mp4", size=100)
        self._make_file("videos/1_intro copy.mp4", size=300)
        self._make_file("videos/2_scene.mp4", size=150)
        self._make_file("videos/2_scene_final.mp4", size=600)
        self._make_file("videos/2_scene_T9zaQ2.mp4", size=450)

        selected = seed_mod._pick_files(self.media_root / "videos")
        names = {p.name for p in selected}
        self.assertIn("1_intro.mp4", names)
        self.assertIn("2_scene.mp4", names)
        self.assertNotIn("1_intro copy.mp4", names)
        self.assertNotIn("2_scene_final.mp4", names)
        self.assertNotIn("2_scene_T9zaQ2.mp4", names)

    def test_pick_files_strips_hash_suffixes(self):
        base = self._make_file("videos/intro.mp4", size=120)
        hashed = self._make_file("videos/intro_KtwWjO_m8phbqY.mp4", size=240)

        selected = seed_mod._pick_files(self.media_root / "videos")
        self.assertEqual({p.name for p in selected}, {base.name})

    def test_build_entries_orders_and_titles(self):
        files = [
            self._make_file("videos/1_Intro aux bougies.mp4"),
            self._make_file("videos/2-1_Pratique.mp4"),
            self._make_file("videos/5_bonus_trucs.mp4"),
        ]
        entries = seed_mod._build_entries(files)

        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0].section_order, 1)
        self.assertEqual(entries[0].lecture_order, 1)
        self.assertEqual(entries[0].title, "Intro aux bougies")

        self.assertEqual(entries[1].section_order, 2)
        self.assertEqual(entries[1].lecture_order, 1)

        bonus_entry = entries[2]
        self.assertEqual(bonus_entry.section_order, 5)
        self.assertEqual(bonus_entry.title, "Bonus trucs")


class ResetAndLoadBougiesTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.media_root = Path(self.tmp.name)
        (self.media_root / "videos").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp.name, ignore_errors=True)

    def _make_video(self, name: str, size: int = 128) -> Path:
        path = self.media_root / "videos" / name
        path.write_bytes(b"0" * size)
        return path

    def _run_loader(self):
        loader.run(script_args=["--media-root", str(self.media_root), "--apply"])

    @override_settings(MEDIA_ROOT="/tmp/unused")
    def test_subdirectories_are_ignored(self):
        self._make_video("1_intro.mp4")
        extra_dir = self.media_root / "videos" / "nested"
        extra_dir.mkdir(parents=True, exist_ok=True)
        (extra_dir / "2_matiere.mp4").write_bytes(b"1" * 10)

        self._run_loader()

        lectures = Lecture.objects.all()
        self.assertEqual(lectures.count(), 1)
        self.assertTrue(lectures.first().video_path.endswith("1_intro.mp4"))

    @override_settings(MEDIA_ROOT="/tmp/unused")
    def test_each_unique_video_creates_one_lecture(self):
        self._make_video("1_intro.mp4", size=100)
        self._make_video("1_intro_HASH.mp4", size=200)
        self._make_video("2_cires.mp4", size=150)

        self._run_loader()

        course = Course.objects.get(slug="bougies-naturelles")
        lectures = Lecture.objects.filter(course=course)
        self.assertEqual(lectures.count(), 2)
        names = {Path(lec.video_path).name for lec in lectures}
        self.assertIn("2_cires.mp4", names)
        self.assertTrue(any(name.startswith("1_intro") for name in names))
        demo_count = lectures.filter(is_demo=True).count()
        self.assertGreaterEqual(demo_count, 1)
