from __future__ import annotations

from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


@override_settings(
    CHATBOT_THROTTLE_RATES={
        "chat_ip": "100/min",
        "chat_session": "100/min",
        "chat_stream": "2/min",
        "chat_send": "10/min",
    }
)
class ChatbotThrottleScopeTests(APITestCase):
    def setUp(self) -> None:
        cache.clear()
        self.client.cookies[settings.CONSENT_COOKIE_NAME] = "accept"
        start_url = reverse("chatbot:start")
        response = self.client.post(start_url, data={})
        self.assertIn(response.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED))
        self.session_id = response.json()["session_id"]
        self.stream_url = reverse("chatbot:stream")
        self.send_url = reverse("chatbot:send")

    def _stream(self):
        return self.client.get(
            self.stream_url,
            data={"session": self.session_id},
            HTTP_ACCEPT="application/json",
        )

    def test_stream_throttle_does_not_block_send(self) -> None:
        for _ in range(2):
            response = self._stream()
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self._stream()
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn("Retry-After", response.headers)

        send_response = self.client.post(
            self.send_url,
            data={"session_id": self.session_id, "message": "Bonjour"},
        )
        self.assertEqual(send_response.status_code, status.HTTP_202_ACCEPTED)

    def test_retry_after_header_present_on_stream_limit(self) -> None:
        latest_response = None
        for _ in range(3):
            latest_response = self._stream()
            if latest_response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
                break
        self.assertIsNotNone(latest_response)
        self.assertEqual(latest_response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        retry_after = latest_response.headers.get("Retry-After")
        self.assertTrue(retry_after)

    def test_stream_within_limit_remains_available(self) -> None:
        for _ in range(2):
            response = self._stream()
            self.assertEqual(response.status_code, status.HTTP_200_OK)
