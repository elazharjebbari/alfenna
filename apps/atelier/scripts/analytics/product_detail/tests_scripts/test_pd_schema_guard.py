from __future__ import annotations

import json
import time
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.test import Client

from apps.atelier.analytics import tasks
from apps.common.runscript_harness import binary_harness


@binary_harness
def run():
    started = time.time()

    client = Client()
    client.cookies[settings.CONSENT_COOKIE_NAME] = "yes"

    bad_payload = {
        "events": [
            {
                "event_uuid": str(uuid4()),
                "event_type": "scroll",
                "page_id": "product_detail",
                "slot_id": "product_hero",
                "component_alias": "",
                "payload": {},
            }
        ]
    }

    bad_response = client.post(
        "/api/analytics/collect/",
        data=json.dumps(bad_payload),
        content_type="application/json",
        HTTP_USER_AGENT="analytics-test/1.0",
    )

    good_payload = {
        "events": [
            {
                "event_uuid": str(uuid4()),
                "event_type": "scroll",
                "page_id": "product_detail",
                "slot_id": "product_hero",
                "component_alias": "",
                "payload": {"scroll_pct": 50},
            }
        ]
    }

    with patch.object(tasks.persist_raw, "delay", side_effect=lambda events, meta=None: tasks.persist_raw.run(events, meta)), \
         patch.object(tasks.rollup_incremental, "delay", side_effect=lambda *args, **kwargs: tasks.rollup_incremental.run(*args, **kwargs)):
        good_response = client.post(
            "/api/analytics/collect/",
            data=json.dumps(good_payload),
            content_type="application/json",
            HTTP_USER_AGENT="analytics-test/1.0",
        )

    ok = bad_response.status_code == 400 and good_response.status_code in (200, 202)

    return {
        "ok": ok,
        "name": "pd_schema_guard",
        "duration": round(time.time() - started, 3),
        "logs": [
            f"bad_status={bad_response.status_code}",
            f"good_status={good_response.status_code}",
        ],
    }
