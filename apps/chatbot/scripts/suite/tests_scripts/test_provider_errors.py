"""Ensure provider errors degrade gracefully."""

from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.urls import reverse

from apps.chatbot.models import ChatSession
from apps.chatbot.providers import ProviderError
from apps.chatbot.services import ChatService


def run() -> None:
    session = ChatSession.objects.create(
        session_key=uuid4().hex,
        consent_snapshot="Y",
        locale="fr",
    )
    segments = SimpleNamespace(consent="Y")

    with patch("apps.chatbot.services.ProviderRouter") as router_cls:
        router = router_cls.return_value
        router.stream.side_effect = ProviderError("offline")
        result = ChatService.handle_message(
            session=session,
            text="Bonjour",
            segments=segments,
        )
        assert result.error == "offline"
        assert result.assistant_message.content.startswith("Je rencontre un souci")

    # Sanity check: API still rejects without consent
    from django.test import Client

    client = Client()
    send_url = reverse("chatbot:send")
    response = client.post(send_url, data={"session_id": str(session.id), "message": "Test"})
    assert response.status_code == 403
