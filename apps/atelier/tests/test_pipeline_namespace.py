from __future__ import annotations

from django.test import RequestFactory, SimpleTestCase

from apps.atelier.compose import pipeline


class PipelineNamespaceTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def _make_request(self, path: str, version: str) -> object:
        request = self.factory.get(path)
        request.site_version = version
        return request

    def test_cache_key_includes_version(self) -> None:
        req_core = self._make_request("/", "core")
        req_ma = self._make_request("/maroc/", "ma")

        page_core = pipeline.build_page_spec("online_home", req_core)
        page_ma = pipeline.build_page_spec("online_home", req_ma)

        core_key = page_core["slots"]["hero"]["cache_key"]
        ma_key = page_ma["slots"]["hero"]["cache_key"]

        self.assertIn("|v:core", core_key)
        self.assertIn("|v:ma", ma_key)
        self.assertNotEqual(core_key, ma_key)

    def test_pages_yaml_respected_per_ns(self) -> None:
        req_core = self._make_request("/", "core")
        req_ma = self._make_request("/maroc/", "ma")

        page_core = pipeline.build_page_spec("test", req_core)
        page_ma = pipeline.build_page_spec("test", req_ma)

        course_core = page_core["slots"]["course_list"]["params"]["label_languages"]
        course_ma = page_ma["slots"]["course_list"]["params"]["label_languages"]

        self.assertNotEqual(course_core, course_ma)
        self.assertEqual(course_core, "Langues : 🇲🇦 / 🇫🇷")
        self.assertEqual(course_ma, "Langues : Arabe / Français")
