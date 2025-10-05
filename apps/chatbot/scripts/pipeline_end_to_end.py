"""End-to-end smoke script for the chatbot pipeline."""

from __future__ import annotations

from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.test import Client
from django.urls import reverse


def run() -> bool:
    client = Client()
    ping_url = reverse("chatbot:ping")

    # Consent gate should block first
    assert client.get(ping_url).status_code == 403

    consent_url = reverse("chatbot:consent")
    consent_response = client.post(consent_url)
    assert consent_response.status_code == 200
    client.cookies[settings.CONSENT_COOKIE_NAME] = "yes"

    start_url = reverse("chatbot:start")
    start_response = client.post(start_url)
    assert start_response.status_code in {200, 201}
    session_id = start_response.json()["session_id"]

    send_url = reverse("chatbot:send")
    send_response = client.post(send_url, data={"session_id": session_id, "message": "Bonjour"}, format="json")
    assert send_response.status_code == 202

    stream_url = reverse("chatbot:stream")
    stream_response = client.get(stream_url, data={"session": session_id}, HTTP_ACCEPT="text/event-stream")
    stream_body = b"".join(stream_response.streaming_content).decode("utf-8")
    assert "event: init" in stream_body
    assert "event: heartbeat" in stream_body

    # Export metrics snapshot
    metrics_out = StringIO()
    call_command("chatbot_metrics", stdout=metrics_out)

    print("Pipeline OK — session=%s" % session_id)
    print(metrics_out.getvalue())
