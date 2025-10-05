"""Consent gate smoke tests."""

from django.conf import settings
from django.test import Client
from django.urls import reverse

from rest_framework.test import APIRequestFactory

from apps.chatbot.views import ChatPingView


def run() -> None:
    client = Client()
    ping_url = reverse("chatbot:ping")

    # Without consent -> forbidden
    response = client.get(ping_url)
    assert response.status_code == 403, response.content

    # Grant consent via endpoint
    consent_url = reverse("chatbot:consent")
    response = client.post(consent_url)
    assert response.status_code == 200, response.content
    cookie = response.cookies.get(settings.CONSENT_COOKIE_NAME)
    assert cookie is not None, "Consent cookie missing"

    factory = APIRequestFactory()
    request = factory.get(ping_url)
    request._segments = type("Segments", (), {"consent": "Y"})()
    response = ChatPingView.as_view()(request)
    assert response.status_code == 200, response.content
