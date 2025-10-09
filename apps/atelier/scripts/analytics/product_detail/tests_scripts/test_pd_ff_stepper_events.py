import json
import time
import uuid
from django.test import Client

NAME = "test_pd_ff_stepper_events"
META = {
    "flow_key": "checkout_intent",
    "step_key": "contact",
    "step_index": 2,
    "step_total": 4,
}


def event(ev_name, extra=None):
    payload = {"ev": ev_name}
    payload.update(META)
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
    batch = {"events": [
        event("ff_step_start"),
        event("ff_step_submit"),
        event("ff_validation_error", {"errors_count": 1}),
        event("ff_step_complete"),
        event("ff_flow_complete", {"total_value": 0}),
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
