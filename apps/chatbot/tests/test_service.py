from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.test import TestCase, override_settings

from apps.chatbot.models import ChatSession, ProviderCall
from apps.chatbot.providers import ProviderChunk, ProviderError
from apps.chatbot.services import ChatService


class ChatServiceTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.session = ChatSession.objects.create(
            session_key="session-test",
            consent_snapshot="Y",
            locale="fr",
        )

    def test_handle_message_requires_consent(self) -> None:
        segments = SimpleNamespace(consent="N")
        with self.assertRaises(PermissionDenied):
            ChatService.handle_message(
                session=self.session,
                text="Bonjour",
                segments=segments,
            )

    @patch("apps.chatbot.services.ProviderRouter")
    def test_handle_message_success(self, router_cls: MagicMock) -> None:
        router = router_cls.return_value
        router.stream.return_value = iter([ProviderChunk(content="Assistant: Bonjour", is_final=True)])

        segments = SimpleNamespace(consent="Y")
        result = ChatService.handle_message(
            session=self.session,
            text="Bonjour",
            segments=segments,
            request_id="req-1",
        )

        self.assertEqual(result.provider, "mock")
        self.assertIsNone(result.error)
        self.assertEqual(result.assistant_message.content, "Assistant: Bonjour")
        self.assertEqual(len(result.chunks), 1)
        self.assertTrue(ProviderCall.objects.filter(session=self.session, status=ProviderCall.STATUS_SUCCESS).exists())

    @patch("apps.chatbot.services.ProviderRouter")
    def test_handle_message_redacts_pii(self, router_cls: MagicMock) -> None:
        router = router_cls.return_value
        router.stream.return_value = iter([
            ProviderChunk(content="Contactez-moi sur example@test.com", is_final=True)
        ])

        segments = SimpleNamespace(consent="Y")
        result = ChatService.handle_message(
            session=self.session,
            text="Bonjour",
            segments=segments,
        )
        self.assertNotIn("@", result.assistant_message.content)
        self.assertIn("[redacted_email]", result.assistant_message.content)

    @patch("apps.chatbot.services.ProviderRouter")
    def test_handle_message_provider_error(self, router_cls: MagicMock) -> None:
        router = router_cls.return_value
        router.stream.side_effect = ProviderError("unavailable")

        segments = SimpleNamespace(consent="Y")
        result = ChatService.handle_message(
            session=self.session,
            text="Bonjour",
            segments=segments,
        )

        self.assertEqual(result.error, "unavailable")
        self.assertEqual(result.chunks[0].content, "Je rencontre un souci temporaire, merci de réessayer ultérieurement.")
        self.assertTrue(ProviderCall.objects.filter(session=self.session, status=ProviderCall.STATUS_ERROR).exists())

    @override_settings(
        CHATBOT_DEFAULT_PROVIDER="openai",
        CHATBOT_PROVIDER_FAILURE_THRESHOLD=1,
        CHATBOT_PROVIDER_CIRCUIT_TTL=60,
    )
    @patch("apps.chatbot.services.ProviderRouter")
    def test_circuit_breaker_falls_back_to_mock(self, router_cls: MagicMock) -> None:
        router = router_cls.return_value

        def side_effect(*, prompt: str, provider: str):
            if provider == "openai":
                raise ProviderError("boom")
            return iter([ProviderChunk(content="Mock fallback", is_final=True)])

        router.stream.side_effect = side_effect

        segments = SimpleNamespace(consent="Y")
        first = ChatService.handle_message(
            session=self.session,
            text="Bonjour",
            segments=segments,
        )
        self.assertEqual(first.error, "boom")
        self.assertEqual(first.provider, "openai")

        second = ChatService.handle_message(
            session=self.session,
            text="Rebonjour",
            segments=segments,
        )
        self.assertEqual(second.provider, "mock")
        self.assertEqual(second.error, "circuit_open")
        self.assertIn("Mock fallback", second.assistant_message.content)
