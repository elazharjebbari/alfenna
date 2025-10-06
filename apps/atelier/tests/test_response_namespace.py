from __future__ import annotations

from django.test import SimpleTestCase, RequestFactory

from apps.atelier.compose.response import render_base, NamespaceTemplateMissing


class ResponseNamespaceTests(SimpleTestCase):
    factory = RequestFactory()

    def _request(self, namespace: str):
        req = self.factory.get("/test")
        req.site_version = namespace
        return req

    def test_screen_template_lookup_namespace_then_core(self) -> None:
        page_ctx = {
            "id": "online_home",
            "slots": {},
            "qa_preview": False,
            "content_rev": "v1",
            "site_version": "ma",
        }
        req = self._request("ma")
        response = render_base(page_ctx, {}, {"css": [], "js": [], "head": []}, req)
        response.render()
        self.assertIn("Version Maroc", response.content.decode("utf-8"))

    def test_missing_screen_template_raises(self) -> None:
        page_ctx = {
            "id": "does_not_exist",
            "slots": {},
            "qa_preview": False,
            "content_rev": "v1",
            "site_version": "ma",
        }
        req = self._request("ma")
        with self.assertRaises(NamespaceTemplateMissing):
            render_base(page_ctx, {}, {"css": [], "js": [], "head": []}, req)
