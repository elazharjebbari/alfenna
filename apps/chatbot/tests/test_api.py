from __future__ import annotations

from uuid import uuid4

from django.conf import settings
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.chatbot.models import ChatMessage, ChatSession


class ChatbotAPITests(APITestCase):
    def setUp(self) -> None:
        cache.clear()
        self.client.cookies[settings.CONSENT_COOKIE_NAME] = "accept"

    def test_start_creates_session(self) -> None:
        url = reverse("chatbot:start")
        response = self.client.post(url, data={})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        payload = response.json()
        self.assertIn("session_id", payload)
        self.assertTrue(ChatSession.objects.filter(id=payload["session_id"]).exists())

    def test_start_with_existing_session_returns_200(self) -> None:
        session = ChatSession.objects.create(
            session_key="existing",
            consent_snapshot="Y",
            locale="fr",
        )
        url = reverse("chatbot:start")
        response = self.client.post(url, data={"session_id": str(session.id)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["session_id"], str(session.id))

    def test_send_records_message(self) -> None:
        start_url = reverse("chatbot:start")
        start_response = self.client.post(start_url)
        session_id = start_response.json()["session_id"]

        send_url = reverse("chatbot:send")
        response = self.client.post(send_url, data={"session_id": session_id, "message": "Bonjour"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        payload = response.json()
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["user"]["content"], "Bonjour")
        self.assertEqual(payload["assistant"]["role"], ChatMessage.ROLE_ASSISTANT)
        self.assertGreaterEqual(len(payload["chunks"]), 1)
        self.assertEqual(payload["provider"], "mock")
        self.assertEqual(ChatMessage.objects.filter(session_id=session_id).count(), 2)

    def test_send_unknown_session_returns_404(self) -> None:
        url = reverse("chatbot:send")
        response = self.client.post(url, data={"session_id": str(uuid4()), "message": "Test"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_history_returns_messages(self) -> None:
        start_response = self.client.post(reverse("chatbot:start"))
        session_id = start_response.json()["session_id"]
        send_url = reverse("chatbot:send")
        self.client.post(send_url, data={"session_id": session_id, "message": "Salut"}, format="json")
        history_url = reverse("chatbot:history")
        response = self.client.get(history_url, data={"session": session_id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.json()
        self.assertEqual(payload["session_id"], session_id)
        self.assertEqual(payload["count"], 2)
        self.assertEqual(payload["messages"][0]["content"], "Salut")
        self.assertIn("Assistant", payload["messages"][1]["content"])

    def test_stream_endpoint_returns_events(self) -> None:
        start_response = self.client.post(reverse("chatbot:start"))
        session_id = start_response.json()["session_id"]
        session = ChatSession.objects.get(pk=session_id)
        ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_ASSISTANT,
            content="Réponse",
        )
        stream_url = reverse("chatbot:stream")
        response = self.client.get(stream_url, data={"session": session_id}, HTTP_ACCEPT="text/event-stream")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "text/event-stream")
        chunks = b"".join(response.streaming_content)
        payload = chunks.decode("utf-8")
        self.assertIn("event: init", payload)
        self.assertIn("event: message", payload)
        self.assertIn("event: done", payload)
        self.assertIn("event: heartbeat", payload)

    def test_session_throttle_limits_requests(self) -> None:
        with self.settings(
            CHATBOT_THROTTLE_RATES={
                "chat_send": "2/min",
                "chat_stream": "100/min",
                "chat_ip": "10/min",
                "chat_session": "100/min",
            }
        ):
            start_response = self.client.post(reverse("chatbot:start"))
            session_id = start_response.json()["session_id"]
            send_url = reverse("chatbot:send")
            for _ in range(2):
                resp = self.client.post(send_url, data={"session_id": session_id, "message": "Hello"}, format="json")
                self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
            throttle_response = self.client.post(send_url, data={"session_id": session_id, "message": "Encore"}, format="json")
            self.assertEqual(throttle_response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_ip_throttle_limits_start_endpoint(self) -> None:
        with self.settings(CHATBOT_THROTTLE_RATES={"chat_ip": "2/min", "chat_session": "10/min"}):
            url = reverse("chatbot:start")
            for _ in range(2):
                resp = self.client.post(url)
                self.assertIn(resp.status_code, {status.HTTP_201_CREATED, status.HTTP_200_OK})
            blocked = self.client.post(url)
            self.assertEqual(blocked.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
