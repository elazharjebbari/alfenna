"""Minimal smoke test for analytics collect endpoint."""

from __future__ import annotations

import json
from uuid import uuid4
from unittest.mock import patch

from django.conf import settings
from django.test import Client


def run() -> None:
    client = Client()
    client.cookies[settings.CONSENT_COOKIE_NAME] = "yes"
    payload = {
        "events": [
            {
                "event_uuid": str(uuid4()),
                "event_type": "view",
                "page_id": "smoke",
                "slot_id": "hero",
                "component_alias": "core/hero",
            }
        ]
    }
    with patch("apps.atelier.analytics.tasks.persist_raw.delay", side_effect=lambda events, meta=None: None), \
         patch("apps.atelier.analytics.tasks.rollup_incremental.delay", side_effect=lambda *args, **kwargs: None):
        response = client.post(
            "/api/analytics/collect/",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_USER_AGENT="analytics-smoke",
        )
    body = getattr(response, "data", None)
    print({"status": response.status_code, "body": body})


__all__ = ["run"]
