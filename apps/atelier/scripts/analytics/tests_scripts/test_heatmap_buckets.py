from __future__ import annotations

import time
from unittest.mock import patch
from uuid import uuid4

from django.utils import timezone

from apps.atelier.analytics import tasks
from apps.atelier.analytics.models import AnalyticsEventRaw, HeatmapBucketDaily


def run():
    started = time.time()
    AnalyticsEventRaw.objects.all().delete()
    HeatmapBucketDaily.objects.all().delete()

    now = timezone.now()
    ts = now.isoformat()
    events = [
        {
            "event_uuid": str(uuid4()),
            "event_type": "heatmap",
            "page_id": "home",
            "slot_id": "hero",
            "component_alias": "core/hero",
            "ts": ts,
            "payload": {"x": 0.42, "y": 0.33},
        },
        {
            "event_uuid": str(uuid4()),
            "event_type": "heatmap",
            "page_id": "home",
            "slot_id": "hero",
            "component_alias": "core/hero",
            "ts": ts,
            "payload": {"x": 0.9999, "y": 0.001},
        },
    ]

    with patch.object(tasks.rollup_incremental, "delay", side_effect=lambda *args, **kwargs: tasks.rollup_incremental.run(*args, **kwargs)):
        tasks.persist_raw.run(events, meta={})

    buckets = list(HeatmapBucketDaily.objects.filter(page_id="home", date=now.date()))
    coords = {(b.bucket_x, b.bucket_y) for b in buckets}
    ok = (42, 33) in coords and (99, 0) in coords

    return {
        "ok": ok,
        "name": __name__,
        "duration": round(time.time() - started, 3),
        "logs": [f"coords={sorted(coords)}"],
    }
