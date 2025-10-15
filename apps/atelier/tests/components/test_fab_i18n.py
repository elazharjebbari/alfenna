from __future__ import annotations

from types import SimpleNamespace

from django.test import RequestFactory, TestCase

from apps.atelier.compose import pipeline


class FabWhatsappI18NTests(TestCase):
    factory = RequestFactory()

    def _request(self, namespace: str, lang: str):
        req = self.factory.get("/", HTTP_ACCEPT_LANGUAGE=lang)
        req.site_version = namespace
        req._segments = SimpleNamespace(
            lang=lang,
            device="desktop",
            consent="Y",
            source="",
            campaign="",
            qa=False,
        )
        req.GET = {}
        req.COOKIES = {}
        req.META.setdefault("SERVER_NAME", "testserver")
        req.META.setdefault("SERVER_PORT", "80")
        req.META.setdefault("HTTP_HOST", "testserver")
        req.META["HTTP_USER_AGENT"] = "pytest"
        req.headers = {"Accept-Language": lang}
        req.LANGUAGE_CODE = lang
        req.user = SimpleNamespace(is_authenticated=False)
        return req

    def _contexts(self, namespace: str):
        page_ctx = {
            "id": "test-page",
            "site_version": namespace,
            "slots": {},
            "qa_preview": False,
            "content_rev": "v1",
        }
        slot_ctx = {
            "id": "fab",
            "alias": "fab/whatsapp",
            "alias_base": "fab/whatsapp",
            "component_namespace": namespace,
            "variant_key": "A",
            "cache": False,
            "cache_key": "",
            "params": {},
            "children": {},
            "content_rev": "v1",
            "children_aliases": [],
            "qa_preview": False,
        }
        return page_ctx, slot_ctx

    def test_label_translated_for_ar_namespace(self) -> None:
        request = self._request(namespace="ma", lang="ar")
        page_ctx, slot_ctx = self._contexts("ma")

        html = pipeline.render_slot_fragment(page_ctx, slot_ctx, request)["html"]

        self.assertIn("هل تحتاج المساعدة؟", html)
        self.assertIn("aria-label=\"التواصل عبر واتساب\"", html)

    def test_label_in_fr_namespace(self) -> None:
        request = self._request(namespace="core", lang="fr")
        page_ctx, slot_ctx = self._contexts("core")

        html = pipeline.render_slot_fragment(page_ctx, slot_ctx, request)["html"]

        self.assertIn("Besoin d’aide ?", html)
        self.assertIn("aria-label=\"Contacter sur WhatsApp\"", html)
