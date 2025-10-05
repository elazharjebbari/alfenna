from django.conf import settings
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.chatbot.models import ConsentEvent


class ChatbotConsentTests(APITestCase):
    def test_ping_requires_consent(self) -> None:
        url = reverse("chatbot:ping")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_ping_with_consent_cookie_returns_ok(self) -> None:
        url = reverse("chatbot:ping")
        self.client.cookies[settings.CONSENT_COOKIE_NAME] = "yes"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "message": "pong"})

    def test_consent_endpoint_sets_cookie(self) -> None:
        url = reverse("chatbot:consent")
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(settings.CONSENT_COOKIE_NAME, response.cookies)
        self.assertEqual(response.cookies[settings.CONSENT_COOKIE_NAME].value, "yes")
        self.assertEqual(ConsentEvent.objects.count(), 1)
