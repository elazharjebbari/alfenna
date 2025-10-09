import json
import time
import uuid
from django.test import Client

NAME = "test_pd_full_journey"
SLOTS = [
    "vendors",
    "header",
    "product_hero",
    "sticky_buybar_v2",
    "before_after_wipe",
    "gallery",
    "faq",
]


def view(slot):
    return {
        "event_uuid": str(uuid.uuid4()),
        "event_type": "view",
        "ts": "2025-01-01T00:00:00.000Z",
        "page_id": "product_detail",
        "slot_id": slot,
        "component_alias": "",
        "payload": {},
    }


def click(name, slot):
    return {
        "event_uuid": str(uuid.uuid4()),
        "event_type": "click",
        "ts": "2025-01-01T00:00:00.000Z",
        "page_id": "product_detail",
        "slot_id": slot,
        "component_alias": "",
        "payload": {"ev": name},
    }


def scroll(pct):
    return {
        "event_uuid": str(uuid.uuid4()),
        "event_type": "scroll",
        "ts": "2025-01-01T00:00:00.000Z",
        "page_id": "product_detail",
        "slot_id": "product_hero",
        "component_alias": "",
        "payload": {"scroll_pct": pct},
    }


def heatmap(x, y):
    return {
        "event_uuid": str(uuid.uuid4()),
        "event_type": "heatmap",
        "ts": "2025-01-01T00:00:00.000Z",
        "page_id": "product_detail",
        "slot_id": "product_hero",
        "component_alias": "",
        "payload": {"x": x, "y": y},
    }


def ff_event(name, extra=None):
    payload = {
        "ev": name,
        "flow_key": "checkout_intent",
        "step_key": "contact",
        "step_index": 2,
        "step_total": 4,
    }
    if extra:
        payload.update(extra)
    return {
        "event_uuid": str(uuid.uuid4()),
        "event_type": "conversion",
        "ts": "2025-01-01T00:00:00.000Z",
        "page_id": "product_detail",
        "slot_id": "sticky_buybar_v2",
        "component_alias": "flowforms",
        "payload": payload,
    }


def run():
    t0 = time.time()
    client = Client()
    events = []
    events.extend(view(slot) for slot in SLOTS)
    events.extend([
        click("hero_cta_primary", "product_hero"),
        click("buybar_cta_click", "sticky_buybar_v2"),
        click("gallery_thumb_click", "gallery"),
        click("faq_item_open", "faq"),
    ])
    events.extend(scroll(p) for p in (25, 50, 75, 90))
    events.extend([heatmap(0.15, 0.22), heatmap(0.88, 0.67)])
    events.extend([
        ff_event("ff_step_start"),
        ff_event("ff_complementary_impression", {
            "slug": "bougie-massage-hydratante",
            "title": "Bougie de massage hydratante",
            "price": "40.00",
            "currency": "MAD",
        }),
        ff_event("ff_complementary_select", {
            "slug": "bougie-massage-hydratante",
            "title": "Bougie de massage hydratante",
            "price": "40.00",
            "currency": "MAD",
        }),
        ff_event("ff_step_submit"),
        ff_event("ff_validation_error", {"errors_count": 1}),
        ff_event("ff_step_complete"),
        ff_event("ff_flow_complete", {"total_value": 0}),
    ])
    response = client.post(
        "/api/analytics/collect/",
        data=json.dumps({"events": list(events)}),
        content_type="application/json",
    )
    ok = response.status_code in (200, 202)
    logs = f"status={response.status_code}, events_sent={len(events)}"
    return {
        "ok": ok,
        "name": NAME,
        "duration": round(time.time() - t0, 3),
        "logs": logs,
    }
