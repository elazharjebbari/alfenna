"""Smoke test for chatbot ping endpoint."""

from django.conf import settings
from django.test import Client
from django.urls import reverse


def run() -> bool:
    client = Client()
    url = reverse("chatbot:ping")

    # Without consent the endpoint must be forbidden
    response = client.get(url)
    assert response.status_code == 403, response.content

    # Simulate consent and retry
    client.cookies[settings.CONSENT_COOKIE_NAME] = "yes"
    response = client.get(url)
    assert response.status_code == 200, response.content
    payload = response.json()
    assert payload.get("status") == "ok", payload
