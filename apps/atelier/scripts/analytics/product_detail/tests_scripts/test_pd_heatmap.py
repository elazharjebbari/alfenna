from __future__ import annotations

import json
import time
from datetime import date
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.test import Client

from apps.atelier.analytics import tasks
from apps.atelier.analytics.models import AnalyticsEventRaw, HeatmapBucketDaily
from apps.common.runscript_harness import binary_harness


@binary_harness
def run():
    started = time.time()

    AnalyticsEventRaw.objects.filter(page_id="product_detail").delete()
    HeatmapBucketDaily.objects.filter(page_id="product_detail").delete()

    client = Client()
    events = [
        {
            "event_uuid": str(uuid4()),
            "event_type": "heatmap",
            "page_id": "product_detail",
            "slot_id": "product_hero",
            "component_alias": "",
            "payload": {"x": 0.25, "y": 0.6},
        },
        {
            "event_uuid": str(uuid4()),
            "event_type": "heatmap",
            "page_id": "product_detail",
            "slot_id": "product_hero",
            "component_alias": "",
            "payload": {"x": 0.8, "y": 0.3},
        },
        {
            "event_uuid": str(uuid4()),
            "event_type": "heatmap",
            "page_id": "product_detail",
            "slot_id": "gallery",
            "component_alias": "",
            "payload": {"x": 0.45, "y": 0.52},
        },
    ]

    with patch.object(tasks.persist_raw, "delay", side_effect=lambda events, meta=None: tasks.persist_raw.run(events, meta)), \
         patch.object(tasks.rollup_incremental, "delay", side_effect=lambda *args, **kwargs: tasks.rollup_incremental.run(*args, **kwargs)):
        client.cookies[settings.CONSENT_COOKIE_NAME] = "yes"
        response = client.post(
            "/api/analytics/collect/",
            data=json.dumps({"events": events}),
            content_type="application/json",
            HTTP_USER_AGENT="analytics-test/1.3",
        )

    buckets = list(HeatmapBucketDaily.objects.filter(page_id="product_detail", date=date.today()))
    coords = sorted((b.bucket_x, b.bucket_y, b.hits) for b in buckets)

    ok = response.status_code in (200, 202) and len(buckets) >= 2 and all(b.hits >= 1 for b in buckets)

    return {
        "ok": ok,
        "name": "pd_heatmap",
        "duration": round(time.time() - started, 3),
        "logs": [f"status={response.status_code}", f"buckets={coords}"],
    }
