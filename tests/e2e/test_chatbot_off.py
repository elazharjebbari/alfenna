"""E2E test ensuring the chatbot leaves no trace when the feature flag is disabled."""
from __future__ import annotations

import os

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

CHATBOT_ENABLED_ENV = os.getenv("CHATBOT_ENABLED", "1").strip().lower()
CHATBOT_DISABLED = CHATBOT_ENABLED_ENV in {"0", "false", "off", "no"}

@pytest.mark.skipif(not CHATBOT_DISABLED, reason="Chatbot flag enabled; OFF variant not under test")
def test_chatbot_fully_absent_when_flag_off(page: Page) -> None:
    page.goto("/")

    expect(page.locator("[data-chatbot]")).to_have_count(0)
    expect(page.locator("script[src*='chatbot']")).to_have_count(0)
    expect(page.locator("link[href*='chatbot']")).to_have_count(0)

    network_hits = page.evaluate(
        """
        () => performance.getEntriesByType('resource')
              .map((entry) => entry.name)
              .filter((name) => name && name.includes('/api/chat/'));
        """
    )
    assert not network_hits, f"Unexpected chat network calls detected: {network_hits}"
