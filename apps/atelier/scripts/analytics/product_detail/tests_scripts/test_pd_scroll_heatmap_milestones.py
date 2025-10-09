import json
import time
import uuid
from django.test import Client

NAME = "test_pd_scroll_heatmap_milestones"


def event(evt_type, payload):
    return {
        "event_uuid": str(uuid.uuid4()),
        "event_type": evt_type,
        "ts": "2025-01-01T00:00:00.000Z",
        "page_id": "product_detail",
        "slot_id": "product_hero",
        "component_alias": "",
        "payload": payload,
    }


def run():
    t0 = time.time()
    client = Client()
    batch = {"events": [
        event("scroll", {"scroll_pct": 25}),
        event("scroll", {"scroll_pct": 50}),
        event("scroll", {"scroll_pct": 75}),
        event("scroll", {"scroll_pct": 90}),
        event("heatmap", {"x": 0.12, "y": 0.33}),
        event("heatmap", {"x": 0.85, "y": 0.64}),
    ]}
    response = client.post(
        "/api/analytics/collect/",
        data=json.dumps(batch),
        content_type="application/json",
    )
    ok = response.status_code in (200, 202)
    return {
        "ok": ok,
        "name": NAME,
        "duration": round(time.time() - t0, 3),
        "logs": f"status={response.status_code}"
    }
