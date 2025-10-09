import json
import time
import uuid
from django.test import Client

NAME = "test_pd_all_ui_clicks"
EVENTS = [
    "header_cta_click",
    "hero_cta_primary",
    "hero_cta_secondary",
    "buybar_cta_click",
    "buybar_select_plan",
    "ba_drag",
    "ba_snap",
    "gallery_thumb_click",
    "gallery_slide_change",
    "faq_item_open",
    "faq_item_close",
]


def slot_for(name):
    if "buybar" in name:
        return "sticky_buybar_v2"
    if "gallery" in name:
        return "gallery"
    if "faq" in name:
        return "faq"
    return "product_hero"


def event(name):
    return {
        "event_uuid": str(uuid.uuid4()),
        "event_type": "click",
        "ts": "2025-01-01T00:00:00.000Z",
        "page_id": "product_detail",
        "slot_id": slot_for(name),
        "component_alias": "",
        "payload": {"ev": name},
    }


def run():
    t0 = time.time()
    client = Client()
    batch = {"events": [event(name) for name in EVENTS]}
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
        "logs": f"status={response.status_code}, sent={len(EVENTS)}"
    }
