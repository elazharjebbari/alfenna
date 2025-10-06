from __future__ import annotations

from importlib import reload

from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import clear_url_caches

from apps.atelier.compose import pipeline


class ChatbotFeatureFlagPipelineTests(TestCase):
    factory = RequestFactory()

    def _build_spec(self):
        request = self.factory.get("/")
        return pipeline.build_page_spec("online_home", request)

    @override_settings(CHATBOT_ENABLED=True)
    def test_slot_present_and_assets_loaded_when_enabled(self) -> None:
        spec = self._build_spec()
        slot_aliases = [str(slot.get("alias") or "") for slot in spec.get("slots", {}).values()]
        self.assertTrue(any(alias.startswith("chatbot/") for alias in slot_aliases))

        assets = pipeline.collect_page_assets(spec)
        joined_assets = "::".join(sum(assets.values(), []))
        self.assertIn("chatbot.js", joined_assets)
        self.assertIn("chatbot.css", joined_assets)
        self.assertIn("|ff:cb:1", spec.get("content_rev", ""))

    @override_settings(CHATBOT_ENABLED=False)
    def test_slots_and_assets_removed_when_disabled(self) -> None:
        spec = self._build_spec()
        slot_aliases = [str(slot.get("alias") or "") for slot in spec.get("slots", {}).values()]
        self.assertFalse(any(alias.startswith("chatbot/") for alias in slot_aliases))

        assets = pipeline.collect_page_assets(spec)
        all_assets = sum(assets.values(), [])
        self.assertTrue(all("chatbot" not in asset for asset in all_assets))
        self.assertIn("|ff:cb:0", spec.get("content_rev", ""))


class ChatbotRoutingFlagTests(TestCase):
    def setUp(self) -> None:
        self.client = Client()

    def _reload_urls(self) -> None:
        clear_url_caches()
        import alfenna.urls as project_urls

        reload(project_urls)

    @override_settings(CHATBOT_ENABLED=False)
    def test_chat_routes_return_404_when_disabled(self) -> None:
        self.addCleanup(self._reload_urls)
        self._reload_urls()
        response = self.client.get("/api/chat/start/")
        self.assertEqual(response.status_code, 404)

    @override_settings(CHATBOT_ENABLED=True)
    def test_chat_routes_mounted_when_enabled(self) -> None:
        self.addCleanup(self._reload_urls)
        self._reload_urls()
        response = self.client.post("/api/chat/start/", data={})
        self.assertNotEqual(response.status_code, 404)
