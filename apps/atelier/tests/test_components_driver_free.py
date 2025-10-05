from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.test import RequestFactory, TestCase

from apps.atelier.components import registry
from apps.atelier.compose import pipeline


class DriverRemovalTests(TestCase):
    factory = RequestFactory()

    def _request(self):
        req = self.factory.get("/")
        req.site_version = "core"
        req._segments = SimpleNamespace(lang="fr", device="desktop", consent="N", source="", campaign="", qa=False)
        req.GET = {}
        req.COOKIES = {}
        req.META = {
            "HTTP_USER_AGENT": "pytest",
            "SERVER_NAME": "testserver",
            "SERVER_PORT": "80",
            "wsgi.url_scheme": "http",
        }
        req.get_host = lambda: "testserver"
        req.headers = {"Accept-Language": "fr"}
        req.user = SimpleNamespace(is_authenticated=False)
        return req

    def _render_slot(self, page_ctx, slot_id: str, request):
        slot = dict(page_ctx["slots"][slot_id])
        slot["cache"] = False
        return pipeline.render_slot_fragment(page_ctx, slot, request)["html"]

    def test_before_after_fragment_has_no_driver_markup(self) -> None:
        request = self._request()
        page_ctx = pipeline.build_page_spec("online_home", request)
        html = self._render_slot(page_ctx, "before_after_wipe", request)

        self.assertIn("ba-wipe", html)
        snippet = html.lower()
        for forbidden in ("driver", "data-tutorial", "shepherd"):
            self.assertNotIn(forbidden, snippet)

    def test_program_roadmap_fragment_has_no_driver_markup(self) -> None:
        request = self._request()
        page_ctx = pipeline.build_page_spec("online_home", request)
        html = self._render_slot(page_ctx, "program_roadmap", request)

        self.assertIn("roadmap", html)
        snippet = html.lower()
        for forbidden in ("driver", "data-tutorial", "shepherd"):
            self.assertNotIn(forbidden, snippet)

    def test_manifests_do_not_reference_driver_assets(self) -> None:
        for alias in ("before-after/wipe", "program/roadmap"):
            comp = registry.get(alias)
            assets = comp.get("assets", {})
            for bucket in ("head", "css", "js", "vendors"):
                for entry in assets.get(bucket, []) or []:
                    self.assertNotIn("driver", entry.lower(), msg=f"Driver asset leaked in {alias}:{bucket}")

    def test_static_sources_have_no_driver_library_calls(self) -> None:
        base = Path(settings.BASE_DIR)
        files = [
            base / "static/components/before-after/wipe.js",
            base / "static/components/before-after/wipe.css",
            base / "static/components/program/roadmap.js",
            base / "static/components/program/roadmap.css",
        ]
        for file_path in files:
            contents = file_path.read_text(encoding="utf-8")
            self.assertNotIn("driver", contents.lower(), msg=f"Driver reference found in {file_path}")
