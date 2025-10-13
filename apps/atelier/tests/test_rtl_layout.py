from __future__ import annotations

from types import SimpleNamespace

from django.template.loader import render_to_string
from django.templatetags.static import static
from django.test import RequestFactory, SimpleTestCase
from django.utils import translation

from apps.atelier.compose import pipeline


class RTLLayoutTests(SimpleTestCase):
    factory = RequestFactory()

    def _base_context(self):
        request = self.factory.get("/")
        request.LANGUAGE_CODE = translation.get_language() or "fr"
        context = {
            "marketing_config": SimpleNamespace(cookie_banner_enabled=False, consent_cookie_name=""),
            "tracking": SimpleNamespace(analytics_enabled=False),
            "page_assets": {"head": [], "css": [], "js": []},
            "slots_html": SimpleNamespace(
                vendors="",
                header="",
                header_struct="",
                footer="",
                footer_main="",
            ),
            "messages": [],
        }
        return request, context

    def test_html_dir_rtl_when_ar(self) -> None:
        with translation.override("ar"):
            request, context = self._base_context()
            request.LANGUAGE_CODE = "ar"
            html = render_to_string("base.html", context=context, request=request)

        self.assertIn('<html lang="ar" dir="rtl">', html)
        self.assertIn('<body class="rtl"', html)

    def test_rtl_styles_included_when_ar(self) -> None:
        with translation.override("ar"):
            request = self.factory.get("/")
            request.site_version = "core"
            request.LANGUAGE_CODE = "ar"
            request._segments = SimpleNamespace(
                lang="ar",
                device="desktop",
                consent="Y",
                source="",
                campaign="",
                qa=False,
            )

            page_ctx = pipeline.build_page_spec("online_home", request)
            assets = pipeline.collect_page_assets(page_ctx)

        self.assertIn(static("css/rtl.css"), assets.get("css", []))
