from __future__ import annotations

import json
import time
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.test import Client

from apps.atelier.analytics import tasks
from apps.atelier.analytics.models import AnalyticsEventRaw, ComponentStatDaily
from apps.common.runscript_harness import binary_harness

SLOTS = [
    "vendors",
    "header",
    "product_hero",
    "sticky_buybar_v2",
    "before_after_wipe",
    "gallery",
    "faq",
]


@binary_harness
def run():
    started = time.time()

    AnalyticsEventRaw.objects.filter(page_id="product_detail").delete()
    ComponentStatDaily.objects.filter(page_id="product_detail").delete()

    client = Client()
    events = [
        {
            "event_uuid": str(uuid4()),
            "event_type": "view",
            "page_id": "product_detail",
            "slot_id": slot,
            "component_alias": "",
            "payload": {},
        }
        for slot in SLOTS
    ]

    payload = {"events": events}

    with patch.object(tasks.persist_raw, "delay", side_effect=lambda events, meta=None: tasks.persist_raw.run(events, meta)), \
         patch.object(tasks.rollup_incremental, "delay", side_effect=lambda *args, **kwargs: tasks.rollup_incremental.run(*args, **kwargs)):
        client.cookies[settings.CONSENT_COOKIE_NAME] = "yes"
        response = client.post(
            "/api/analytics/collect/",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_USER_AGENT="analytics-test/1.0",
        )

    raw_count = AnalyticsEventRaw.objects.filter(page_id="product_detail").count()
    aggregates = ComponentStatDaily.objects.filter(page_id="product_detail")
    aggregate_slots = {item.slot_id for item in aggregates}

    ok = response.status_code in (200, 202) and raw_count == len(events) and set(SLOTS).issubset(aggregate_slots)

    return {
        "ok": ok,
        "name": "pd_collect_smoke",
        "duration": round(time.time() - started, 3),
        "logs": [
            f"status={response.status_code}",
            f"raw={raw_count}",
            f"aggregates={len(aggregate_slots)}",
        ],
    }
