import json
import time
import uuid
from django.test import Client

NAME = "test_pd_step2_complementary_payloads"


def _event(name):
    payload = {
        "ev": name,
        "slug": "bougie-massage-hydratante",
        "title": "Bougie de massage hydratante",
        "price": "40.00",
        "currency": "MAD",
    }
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
    started = time.time()
    client = Client()
    batch = {
        "events": [
            _event("ff_complementary_impression"),
            _event("ff_complementary_select"),
        ]
    }
    response = client.post(
        "/api/analytics/collect/",
        data=json.dumps(batch),
        content_type="application/json",
    )
    ok = response.status_code in (200, 202)
    return {
        "ok": ok,
        "name": NAME,
        "duration": round(time.time() - started, 3),
        "logs": f"status={response.status_code}, events={len(batch['events'])}",
    }
