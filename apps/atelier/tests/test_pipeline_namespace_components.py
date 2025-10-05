from __future__ import annotations

from types import SimpleNamespace

from django.test import TestCase, RequestFactory

from apps.atelier.compose import pipeline


class PipelineNamespaceComponentTests(TestCase):
    factory = RequestFactory()

    def _request(self, namespace: str):
        req = self.factory.get("/")
        req.site_version = namespace
        req._segments = SimpleNamespace(lang="fr", device="d", consent="N", source="", campaign="", qa=False)
        req.GET = {}
        req.COOKIES = {}
        req.META = {"HTTP_USER_AGENT": "pytest"}
        req.headers = {"Accept-Language": "fr"}
        req.user = SimpleNamespace(is_authenticated=False, first_name="")
        return req

    def test_page_uses_namespace_component_override(self) -> None:
        req = self._request("ma")
        page_ctx = pipeline.build_page_spec("online_home", req)
        contact_slot = page_ctx["slots"]["contact_info"]
        contact_slot = dict(contact_slot)
        contact_slot["cache"] = False
        html = pipeline.render_slot_fragment(page_ctx, contact_slot, req)["html"]
        self.assertIn("+212 600 000 000", html)

    def test_page_falls_back_to_core_component(self) -> None:
        req = self._request("fr")
        page_ctx = pipeline.build_page_spec("online_home", req)
        contact_slot = page_ctx["slots"]["contact_info"]
        contact_slot = dict(contact_slot)
        contact_slot["cache"] = False
        html = pipeline.render_slot_fragment(page_ctx, contact_slot, req)["html"]
        self.assertIn("+33 1 23 45 67 89", html)
