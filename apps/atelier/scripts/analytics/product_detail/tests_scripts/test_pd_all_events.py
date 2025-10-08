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

SLOTS = {
    "header": "header_cta_click",
    "product_hero": "hero_cta_primary",
    "before_after_wipe": "ba_drag",
    "gallery": "gallery_slide_change",
    "faq": "faq_item_open",
}


@binary_harness
def run():
    started = time.time()

    AnalyticsEventRaw.objects.filter(page_id="product_detail").delete()
    ComponentStatDaily.objects.filter(page_id="product_detail").delete()

    client = Client()
    events = []

    for slot, event_name in SLOTS.items():
        payload = {"ev": event_name}
        if event_name == "ba_drag":
            payload["percent"] = 42
        if event_name == "gallery_slide_change":
            payload["to_idx"] = 2
        if event_name == "faq_item_open":
            payload["id"] = "objections"
        events.append(
            {
                "event_uuid": str(uuid4()),
                "event_type": "click",
                "page_id": "product_detail",
                "slot_id": slot,
                "component_alias": "",
                "payload": payload,
            }
        )

    # Scroll depth milestones
    events.extend(
        [
            {
                "event_uuid": str(uuid4()),
                "event_type": "scroll",
                "page_id": "product_detail",
                "slot_id": "",
                "component_alias": "",
                "payload": {"scroll_pct": pct},
            }
            for pct in (25, 50)
        ]
    )

    payload = {"events": events}

    with patch.object(tasks.persist_raw, "delay", side_effect=lambda events, meta=None: tasks.persist_raw.run(events, meta)), \
         patch.object(tasks.rollup_incremental, "delay", side_effect=lambda *args, **kwargs: tasks.rollup_incremental.run(*args, **kwargs)):
        client.cookies[settings.CONSENT_COOKIE_NAME] = "yes"
        response = client.post(
            "/api/analytics/collect/",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_USER_AGENT="analytics-test/1.2",
        )

    stats = ComponentStatDaily.objects.filter(page_id="product_detail")
    slot_clicks = {
        slot: stats.filter(slot_id=slot).values_list("clicks", flat=True).first() or 0 for slot in SLOTS
    }
    scroll_avg = stats.filter(slot_id="").values_list("avg_scroll_pct", flat=True).first() or 0.0
    inserted = AnalyticsEventRaw.objects.filter(page_id="product_detail").count()

    ok = (
        response.status_code in (200, 202)
        and inserted == len(events)
        and all(count >= 1 for count in slot_clicks.values())
        and abs(float(scroll_avg) - 37.5) <= 0.5
    )

    logs = [
        f"status={response.status_code}",
        f"inserted={inserted}",
        f"clicks={slot_clicks}",
        f"scroll_avg={float(scroll_avg):.2f}",
    ]

    return {
        "ok": ok,
        "name": "pd_all_events",
        "duration": round(time.time() - started, 3),
        "logs": logs,
    }
