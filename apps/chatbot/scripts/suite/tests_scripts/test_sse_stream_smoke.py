"""SSE endpoint smoke test ensuring low-latency first chunk."""

from time import perf_counter

from django.conf import settings
from django.test import Client
from django.urls import reverse


def run() -> None:
    client = Client()
    client.cookies[settings.CONSENT_COOKIE_NAME] = "yes"

    start_response = client.post(reverse("chatbot:start"))
    assert start_response.status_code in {200, 201}, start_response.content
    session_id = start_response.json()["session_id"]

    from apps.chatbot.models import ChatMessage, ChatSession

    session = ChatSession.objects.get(pk=session_id)
    ChatMessage.objects.create(
        session=session,
        role=ChatMessage.ROLE_ASSISTANT,
        content="Salut",
    )

    stream_url = reverse("chatbot:stream")
    t0 = perf_counter()
    response = client.get(stream_url, {"session": session_id})
    stream_iter = iter(response.streaming_content)
    first_chunk = next(stream_iter)
    elapsed_ms = (perf_counter() - t0) * 1000
    assert elapsed_ms <= 250, f"First chunk too slow: {elapsed_ms} ms"
    payload = first_chunk.decode("utf-8")
    assert "event: init" in payload, payload
