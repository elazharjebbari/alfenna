from __future__ import annotations

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.chatbot.models import ChatMessage, ChatSession


class ChatbotManagementTests(TestCase):
    def setUp(self) -> None:
        self.session = ChatSession.objects.create(
            session_key="session-management",
            consent_snapshot="Y",
            locale="fr",
        )
        ChatMessage.objects.create(
            session=self.session,
            role=ChatMessage.ROLE_USER,
            content="Bonjour",
        )

    def test_metrics_command_outputs_summary(self) -> None:
        buffer = StringIO()
        call_command("chatbot_metrics", stdout=buffer)
        output = buffer.getvalue()
        self.assertIn("Chatbot metrics summary", output)
        self.assertIn("sessions_total", output)

    def test_purge_command_removes_old_messages(self) -> None:
        stale = ChatMessage.objects.create(
            session=self.session,
            role=ChatMessage.ROLE_ASSISTANT,
            content="Ancien",
        )
        ChatMessage.objects.filter(pk=stale.pk).update(
            created_at=timezone.now() - timedelta(days=40)
        )
        call_command("purge_chatbot_history", days=30)
        self.assertFalse(ChatMessage.objects.filter(pk=stale.pk).exists())
