from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import mock

from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings

from apps.atelier.ab.waffle import resolve_variant
from apps.atelier import services
from apps.atelier.compose.pipeline import build_page_spec
from apps.atelier.config import loader


class TestABCookie(TestCase):
    @override_settings(DEBUG=False)
    def test_ab_cookie_middleware_sets_cookie_for_anonymous(self):
        client = Client()
        response = client.get("/")

        self.assertIn(response.status_code, {200, 302})
        cookie = response.cookies.get("ll_ab")
        self.assertIsNotNone(cookie)
        self.assertGreaterEqual(len(cookie.value), 16)
        self.assertEqual(cookie["samesite"].lower(), "lax")
        self.assertTrue(cookie["secure"])


class TestResolveVariant(TestCase):
    def setUp(self) -> None:
        self.rf = RequestFactory()

    @mock.patch("apps.atelier.ab.waffle._stable_bucket", return_value=3)
    def test_resolve_variant_respects_rollout(self, _bucket):
        request = self.rf.get("/")
        variants = {"A": "x/a", "B": "x/b"}

        with mock.patch("apps.atelier.ab.waffle.get_experiments_spec", return_value={"hero_v2": {"rollout": 1}}):
            variant, alias = resolve_variant("hero_v2", variants, request)
            self.assertEqual((variant, alias), ("A", "x/a"))

        with mock.patch("apps.atelier.ab.waffle.get_experiments_spec", return_value={"hero_v2": {"rollout": 5}}):
            variant, alias = resolve_variant("hero_v2", variants, request)
            self.assertEqual((variant, alias), ("B", "x/b"))

    def test_resolve_variant_fallsback_to_A_if_B_missing(self):
        request = self.rf.get("/")
        variant, alias = resolve_variant("hero_v2", {"A": "x/a"}, request)
        self.assertEqual((variant, alias), ("A", "x/a"))


class TestExperimentsLoader(SimpleTestCase):
    def tearDown(self) -> None:
        loader.clear_config_cache()

    def test_get_experiments_spec_merges_core_and_namespace(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            cfg_root = base / "configs" / "atelier"
            (cfg_root / "core").mkdir(parents=True)
            (cfg_root / "fr").mkdir(parents=True)

            (cfg_root / "core" / "experiments.yml").write_text(
                "experiments:\n  header_ab:\n    rollout: 50\n    variants:\n      A: core/a\n  shared:\n    value: 1\n",
                encoding="utf-8",
            )
            (cfg_root / "fr" / "experiments.yml").write_text(
                "experiments:\n  header_ab:\n    rollout: 25\n    extra: fr-only\n  local_only:\n    rollout: 10\n",
                encoding="utf-8",
            )

            rf = RequestFactory()
            request = rf.get("/")
            request.site_version = "fr"

            with override_settings(BASE_DIR=base):
                with mock.patch("apps.atelier.config.loader.CFG_ROOT", cfg_root):
                    loader.clear_config_cache()
                    spec = loader.get_experiments_spec(request=request)

        self.assertEqual(spec["header_ab"]["rollout"], 25)
        self.assertEqual(spec["header_ab"]["variants"], {"A": "core/a"})
        self.assertEqual(spec["header_ab"]["extra"], "fr-only")
        self.assertIn("shared", spec)
        self.assertIn("local_only", spec)


class TestCacheKeys(TestCase):
    def setUp(self) -> None:
        self.rf = RequestFactory()

    def test_cache_key_differs_across_variants(self):
        request_a = self.rf.get("/")
        request_a.site_version = "core"

        with mock.patch("apps.atelier.compose.pipeline.get_experiments_spec", return_value={"header_ab": {"rollout": 50}}), \
             mock.patch("apps.atelier.ab.waffle.get_experiments_spec", return_value={"header_ab": {"rollout": 50}}), \
             mock.patch("apps.atelier.ab.waffle._stable_bucket", return_value=88):
            page_ctx_a = build_page_spec("online_home", request_a)

        header_a = page_ctx_a["slots"]["header"]
        self.assertEqual(header_a["variant_key"], "A")

        request_b = self.rf.get("/")
        request_b.site_version = "core"

        with mock.patch("apps.atelier.compose.pipeline.get_experiments_spec", return_value={"header_ab": {"rollout": 50}}), \
             mock.patch("apps.atelier.ab.waffle.get_experiments_spec", return_value={"header_ab": {"rollout": 50}}), \
             mock.patch("apps.atelier.ab.waffle._stable_bucket", return_value=3):
            page_ctx_b = build_page_spec("online_home", request_b)

        header_b = page_ctx_b["slots"]["header"]
        self.assertEqual(header_b["variant_key"], "B")

        seg_a = services.get_segments(request_a)
        seg_b = services.get_segments(request_b)

        key_a = services.build_cache_key(
            page_id="online_home",
            slot_id="header",
            variant_key=header_a["variant_key"],
            segments=seg_a,
            content_rev=header_a["content_rev"],
            site_version=header_a["component_namespace"],
        )

        key_b = services.build_cache_key(
            page_id="online_home",
            slot_id="header",
            variant_key=header_b["variant_key"],
            segments=seg_b,
            content_rev=header_b["content_rev"],
            site_version=header_b["component_namespace"],
        )

        self.assertNotEqual(key_a, key_b)

    @mock.patch("apps.atelier.ab.waffle._stable_bucket", return_value=88)
    def test_preview_qa_does_not_change_variant_but_changes_cache_key(self, _bucket):
        normal_request = self.rf.get("/")
        normal_request.site_version = "core"
        with mock.patch("apps.atelier.compose.pipeline.get_experiments_spec", return_value={"header_ab": {"rollout": 50}}), \
             mock.patch("apps.atelier.ab.waffle.get_experiments_spec", return_value={"header_ab": {"rollout": 50}}):
            normal_ctx = build_page_spec("online_home", normal_request)
        header_normal = normal_ctx["slots"]["header"]

        qa_request = self.rf.get("/?dwft_header_ab=1")
        qa_request.site_version = "core"
        with mock.patch("apps.atelier.compose.pipeline.get_experiments_spec", return_value={"header_ab": {"rollout": 50}}), \
             mock.patch("apps.atelier.ab.waffle.get_experiments_spec", return_value={"header_ab": {"rollout": 50}}):
            qa_ctx = build_page_spec("online_home", qa_request)
        header_qa = qa_ctx["slots"]["header"]

        self.assertEqual(header_normal["variant_key"], header_qa["variant_key"])
        self.assertTrue(header_qa["qa_preview"])

        seg = services.get_segments(qa_request)
        normal_key = services.build_cache_key(
            page_id="online_home",
            slot_id="header",
            variant_key=header_normal["variant_key"],
            segments=seg,
            content_rev=header_normal["content_rev"],
            site_version=header_normal["component_namespace"],
        )
        qa_key = services.build_cache_key(
            page_id="online_home",
            slot_id="header",
            variant_key=header_qa["variant_key"],
            segments=seg,
            content_rev=header_qa["content_rev"],
            qa=True,
            site_version=header_qa["component_namespace"],
        )

        self.assertNotEqual(normal_key, qa_key)
        self.assertTrue(qa_key.endswith("|qa"))


class TestHeaderRendering(TestCase):
    def setUp(self) -> None:
        self.client = Client()

    @mock.patch("apps.atelier.ab.waffle._stable_bucket", return_value=88)
    def test_header_renders_variant_a(self, _bucket):
        with mock.patch("apps.atelier.compose.pipeline.get_experiments_spec", return_value={"header_ab": {"rollout": 0}}), \
             mock.patch("apps.atelier.ab.waffle.get_experiments_spec", return_value={"header_ab": {"rollout": 0}}):
            response = self.client.get("/")
        self.assertContains(response, 'data-ab-variant="A"')

    @mock.patch("apps.atelier.ab.waffle._stable_bucket", return_value=3)
    def test_header_renders_variant_b(self, _bucket):
        with mock.patch("apps.atelier.compose.pipeline.get_experiments_spec", return_value={"header_ab": {"rollout": 100}}), \
             mock.patch("apps.atelier.ab.waffle.get_experiments_spec", return_value={"header_ab": {"rollout": 100}}):
            response = self.client.get("/")
        self.assertContains(response, 'data-ab-variant="B"')
