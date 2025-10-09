import json
import time
from django.test import Client

NAME = "test_pd_schema_guard"


def run():
    t0 = time.time()
    client = Client()
    bad = {
        "events": [{
            "event_uuid": "00000000-0000-4000-8000-000000000001",
            "event_type": "scroll",
            "ts": "2025-01-01T00:00:00.000Z",
            "page_id": "product_detail",
            "slot_id": "product_hero",
            "component_alias": "",
            "payload": {}
        }]
    }
    response = client.post(
        "/api/analytics/collect/",
        data=json.dumps(bad),
        content_type="application/json",
    )
    ok = response.status_code >= 400
    return {
        "ok": ok,
        "name": NAME,
        "duration": round(time.time() - t0, 3),
        "logs": f"status={response.status_code}"
    }
