from __future__ import annotations

from types import SimpleNamespace

from django.test import RequestFactory, TestCase

from apps.atelier.components import registry
from apps.atelier.compose import pipeline


class FooterI18NTests(TestCase):
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
            "language_bidi": False,
        }
        slot_ctx = {
            "id": "footer",
            "alias": "footer/main",
            "alias_base": "footer/main",
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

    def test_manifest_uses_translatable_keys(self) -> None:
        meta = registry.get("footer/main", namespace="core")
        params = meta.get("params", {})
        self.assertEqual(params.get("brand_title"), "footer.brand")
        self.assertEqual(params.get("shop_title"), "footer.section.shop")
        self.assertEqual(params.get("support_title"), "footer.section.support")
        self.assertEqual(params.get("quick_title"), "footer.section.quick_links")
        links_shop = [item["label"] for item in params.get("links_shop", [])]
        self.assertTrue(all(label.startswith("footer.links.shop.") for label in links_shop))
        links_contact = [item["label"] for item in params.get("links_contact", [])]
        self.assertTrue(all(label.startswith("footer.links.contact.") for label in links_contact))
        links_quick = [item["label"] for item in params.get("links_quick", [])]
        self.assertTrue(all(label.startswith("footer.links.quick.") for label in links_quick))
        self.assertEqual(params.get("copyright_tail_html"), "footer.copyright_tail_html")

    def test_footer_translated_in_arabic_namespace(self) -> None:
        request = self._request(namespace="ma", lang="ar")
        page_ctx, slot_ctx = self._contexts("ma")

        html = pipeline.render_slot_fragment(page_ctx, slot_ctx, request)["html"]

        self.assertIn("المتجر", html)
        self.assertIn("نصائح الاستخدام", html)
        self.assertIn("الدعم", html)
        self.assertIn("روابط سريعة", html)
        self.assertIn("صُنع بحب", html)

    def test_footer_defaults_in_core_namespace(self) -> None:
        request = self._request(namespace="core", lang="fr")
        page_ctx, slot_ctx = self._contexts("core")

        html = pipeline.render_slot_fragment(page_ctx, slot_ctx, request)["html"]

        self.assertIn("Boutique", html)
        self.assertIn("Conseils d’utilisation", html)
        self.assertIn("Support", html)
        self.assertIn("Liens rapides", html)
        self.assertIn("Made with", html)
