from __future__ import annotations

import copy
from types import SimpleNamespace

from django.test import TestCase, RequestFactory

from apps.atelier.components import registry
from apps.atelier.compose import pipeline


class PipelineI18nIntegrationTests(TestCase):
    factory = RequestFactory()

    def setUp(self) -> None:
        super().setUp()
        self._components = registry._COMPONENTS  # type: ignore[attr-defined]
        self._snapshot = copy.deepcopy(self._components)

        registry.register(
            "test/i18n-component",
            "components/test/i18n_component.html",
            namespace="core",
            params={"title": "t:header.menu.home"},
        )
        registry.register(
            "test/i18n-component",
            "components/test/i18n_component.html",
            namespace="ma",
            params={"title": "t:header.menu.home"},
        )

    def tearDown(self) -> None:
        self._components.clear()
        for namespace, components in self._snapshot.items():
            self._components[namespace] = components
        super().tearDown()

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
        req.LANGUAGE_CODE = lang
        req.user = SimpleNamespace(is_authenticated=False, first_name="")
        return req

    def _contexts(self, namespace: str, params: dict[str, str]):
        page_ctx = {
            "id": "test-page",
            "site_version": namespace,
            "slots": {},
            "qa_preview": False,
            "content_rev": "v1",
        }
        slot_ctx = {
            "id": "hero",
            "alias": "test/i18n-component",
            "alias_base": "test/i18n-component",
            "component_namespace": namespace,
            "variant_key": "A",
            "cache": False,
            "cache_key": "",
            "params": params,
            "children": {},
            "content_rev": "v1",
            "children_aliases": [],
            "qa_preview": False,
        }
        return page_ctx, slot_ctx

    def test_params_are_translated_before_render(self) -> None:
        request = self._request(namespace="ma", lang="ar")
        page_ctx, slot_ctx = self._contexts("ma", {"title": "t:header.menu.home"})

        html = pipeline.render_slot_fragment(page_ctx, slot_ctx, request)["html"]

        self.assertIn("الرئيسية", html)

    def test_noop_when_keys_absent(self) -> None:
        request = self._request(namespace="ma", lang="ar")
        page_ctx, slot_ctx = self._contexts("ma", {"title": "NotAKey"})

        html = pipeline.render_slot_fragment(page_ctx, slot_ctx, request)["html"]

        self.assertIn("NotAKey", html)

    def test_dict_token_is_translated(self) -> None:
        request = self._request(namespace="ma", lang="ar")
        page_ctx, slot_ctx = self._contexts("ma", {"title": {"t": "header.menu.contact"}})

        html = pipeline.render_slot_fragment(page_ctx, slot_ctx, request)["html"]

        self.assertIn("تواصل معنا", html)
