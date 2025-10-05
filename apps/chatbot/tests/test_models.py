from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.chatbot.models import ChatMessage, ChatSession, ConsentEvent
from apps.chatbot.tasks import purge_chat_messages_older_than


class ChatbotModelTests(TestCase):
    def setUp(self) -> None:
        self.session = ChatSession.objects.create(
            session_key="session-test",
            consent_snapshot="Y",
            locale="fr",
        )

    def test_chat_message_cascade_on_session_delete(self) -> None:
        ChatMessage.objects.create(
            session=self.session,
            role=ChatMessage.ROLE_USER,
            content="Bonjour",
        )
        self.assertEqual(ChatMessage.objects.count(), 1)
        self.session.delete()
        self.assertEqual(ChatMessage.objects.count(), 0)

    def test_consent_event_links_to_user(self) -> None:
        user_model = get_user_model()
        user = user_model.objects.create_user(username="tester", password="pass")
        event = ConsentEvent.objects.create(
            session=self.session,
            user=user,
            value="Y",
            ip="127.0.0.1",
            user_agent="pytest",
        )
        self.assertEqual(event.user.username, "tester")

    def test_purge_chat_messages_older_than(self) -> None:
        recent = ChatMessage.objects.create(
            session=self.session,
            role=ChatMessage.ROLE_ASSISTANT,
            content="Réponse récente",
        )
        stale = ChatMessage.objects.create(
            session=self.session,
            role=ChatMessage.ROLE_USER,
            content="Ancien message",
        )
        cutoff = timezone.now() - timedelta(days=40)
        ChatMessage.objects.filter(pk=stale.pk).update(created_at=cutoff)

        deleted = purge_chat_messages_older_than(days=30)
        self.assertEqual(deleted, 1)
        self.assertTrue(ChatMessage.objects.filter(pk=recent.pk).exists())
        self.assertFalse(ChatMessage.objects.filter(pk=stale.pk).exists())
