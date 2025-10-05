from __future__ import annotations

import re

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings


@override_settings(CHATBOT_ENABLED=True)
class ChatbotUITests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        cache.clear()

    def test_chatbot_renders_with_consent_gate_when_cookie_absent(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()

        self.assertIn("data-chatbot", html)
        self.assertIn("data-chatbot-trigger", html)
        self.assertIn("data-chatbot-panel", html)
        self.assertIn("data-chatbot-consent-accept", html)
        self.assertRegex(html, r"data-chatbot-textarea[^>]*disabled")

    def test_chatbot_renders_unlocked_when_consent_cookie_present(self) -> None:
        self.client.cookies[settings.CONSENT_COOKIE_NAME] = "yes"
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()

        self.assertIn("data-chatbot", html)
        self.assertIn("data-chatbot-messages", html)
        self.assertNotIn("data-chatbot-consent-accept", html)
        self.assertNotRegex(html, r"data-chatbot-textarea[^>]*disabled")
